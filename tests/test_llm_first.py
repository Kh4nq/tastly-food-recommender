"""LLM-first regressions: authored turns, no live APIs, datasets or model loads."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from common.schemas import PreferenceUpdate, PreviousResult, UserPreferenceState, UserRequest
from conversation.config import ConversationConfig
from conversation.providers.base import ProviderError
from conversation.safety import validate_model_delta
from conversation.service import process_user_request
from conversation.slm.base import SLMParseResult


def turn(intent="search", delta=None, reply=None, evidence=()):
    delta = delta or PreferenceUpdate()
    return {"intent": intent, "reply": reply, "evidence": [{"field": field, "quote": quote} for field, quote in evidence],
        "preferences": {"set_values": {"food": None, "cuisine": None, "location": None, **delta.set_values},
            "add_hard_constraints": [{"key": k, "value": v} for k, v in delta.add_hard_constraints.items()],
            "add_soft_preferences": [{"key": k, "value": v} for k, v in delta.add_soft_preferences.items()],
            "add_semantic_preferences": delta.add_semantic_preferences, "add_negative_preferences": delta.add_negative_preferences,
            "context_updates": [{"key": k, "value": v} for k, v in delta.context_updates.items()],
            "remove_preferences": delta.remove_preferences, "references": delta.references,
            "relative_updates": {"budget": None, "distance": None, **delta.relative_updates}}}


def wire_provider(result):
    return SimpleNamespace(interpret_turn=Mock(side_effect=result if isinstance(result, Exception) else None,
        return_value=None if isinstance(result, Exception) else result), close=Mock(),
        last_attempts=1, last_usage={"input_tokens": 20, "output_tokens": 10}, last_cost_usd=None)


def run(monkeypatch, message, primary, backup=None, *, state=None, config=None, **kwargs):
    first = wire_provider(primary)
    second = wire_provider(backup if backup is not None else ProviderError("offline backup"))
    monkeypatch.setattr("conversation.llm_first.create_provider", lambda _: first)
    monkeypatch.setattr("conversation.llm_first.create_chain_provider", lambda _, **kw: second)
    config = config or ConversationConfig(llm_provider="openrouter_chain")
    result = process_user_request(UserRequest(session_id="S", message=message, current_state=state,
        **{k: v for k, v in kwargs.items() if k != "slm_provider"}), config=config, slm_provider=kwargs.get("slm_provider"))
    return result, first, second


@pytest.mark.parametrize("message,food,budget,distance", [
    ("Phở chay dưới 100k cách tôi 3km", "phở chay", 100000, 3),
    ("Phở chay dưới 100k trong vòng 3km", "phở chay", 100000, 3),
    ("Tìm ramen dưới 150k trong 3km", "ramen", 150000, 3),
    ("Find vegetarian pho under 100k within 3 km", "vegetarian pho", 100000, 3),
    ("vegetarian pho under one hundred thousand VND within three kilometers", "vegetarian pho", 100000, 3),
    ("pho chay <100k cach toi 3km", "pho chay", 100000, 3),
    ("ramen tối đa 150.000đ cách 500m", "ramen", 150000, .5),
    ("ramen dưới 150.000 đồng trong 3km", "ramen", 150000, 3),
])
def test_natural_search_is_one_call_without_rule_first(monkeypatch, message, food, budget, distance):
    monkeypatch.setattr("conversation.rule_parser.parse_by_rules_detailed", Mock(side_effect=AssertionError("No mandatory rules")))
    delta = PreferenceUpdate(set_values={"food": [food]}, add_hard_constraints={"budget_max": budget, "max_distance_km": distance})
    if "chay" in message or "vegetarian" in message:
        delta.add_hard_constraints["vegetarian"] = True
    result, first, backup = run(monkeypatch, message, turn(delta=delta))
    assert result.state.food == [food]
    assert result.state.hard_constraints == delta.add_hard_constraints
    assert not result.metadata.clarification_required
    assert result.metadata.parser_used == "llm" and result.metadata.rule_parse_ms == 0
    first.interpret_turn.assert_called_once()
    assert first.interpret_turn.call_args.kwargs["rule_update"] is None
    backup.interpret_turn.assert_not_called()


def test_3km_evidence_regression_also_fixed_in_legacy_validator():
    delta = PreferenceUpdate(set_values={"food": ["phở chay"]}, add_hard_constraints={"vegetarian": True, "budget_max": 100000, "max_distance_km": 3})
    request = UserRequest(session_id="S", message="Phở chay dưới 100k cách tôi 3km")
    validate_model_delta(delta, request, request.message, set())


@pytest.mark.parametrize("message,intent,reply", [
    ("Phở khác bún như thế nào?", "informational", "Phở thường dùng bánh phở dẹt, còn bún là sợi tròn; nước dùng và cách chế biến cũng khác nhau."),
    ("Chào bạn", "conversation", "Chào bạn! Mình có thể giúp bạn tìm món hoặc tìm hiểu về món ăn."),
    ("Hello there", "conversation", "Chào bạn! Bạn muốn tìm hiểu món ăn nào?"),
    ("What's the difference between pho and bun?", "informational", "Phở thường có sợi dẹt, còn bún có sợi tròn."),
])
def test_nonsearch_preserves_state_exactly(monkeypatch, message, intent, reply):
    state = UserPreferenceState(session_id="S", food=["ramen"], hard_constraints={"allergens_excluded": ["milk"], "budget_max": 150000})
    before = state.model_dump()
    result, first, backup = run(monkeypatch, message, turn(intent, reply=reply), state=state)
    assert result.state.model_dump() == before and result.state is not state
    assert result.metadata.intent == intent and result.metadata.assistant_message == reply
    assert result.metadata.state_preserved and not result.metadata.clarification_required
    assert not any(result.preference_update.model_dump().values())
    assert state.model_dump() == before
    first.interpret_turn.assert_called_once(); backup.interpret_turn.assert_not_called()


def test_refinement_retains_prior_food_allergies_and_budget_without_numeric_policy(monkeypatch):
    state = UserPreferenceState(session_id="S", food=["ramen"], hard_constraints={"budget_max": 100000, "allergens_excluded": ["milk", "peanut"]})
    quiet, _, _ = run(monkeypatch, "Tôi muốn quán yên tĩnh hơn", turn("refinement", PreferenceUpdate(add_semantic_preferences=["quiet"])), state=state)
    assert quiet.state.semantic_preferences == ["quiet"] and quiet.state.hard_constraints == state.hard_constraints
    cheaper, _, _ = run(monkeypatch, "Make it cheaper", turn("refinement", PreferenceUpdate(relative_updates={"budget": "decrease"})), state=quiet.state)
    assert cheaper.preference_update.relative_updates == {"budget": "decrease"}
    assert cheaper.state.hard_constraints == state.hard_constraints and "relative_updates" not in cheaper.state.context
    final, _, _ = run(monkeypatch, "Change my budget to 80k", turn("refinement", PreferenceUpdate(add_hard_constraints={"budget_max": 80000})), state=cheaper.state)
    assert final.state.food == ["ramen"] and final.state.hard_constraints["budget_max"] == 80000
    assert final.state.hard_constraints["allergens_excluded"] == ["milk", "peanut"]


def test_numeric_refinement_accepts_word_units_without_canonical_field_name(monkeypatch):
    state = UserPreferenceState(session_id="S", food=["ramen"], hard_constraints={"budget_max": 150000})
    result, _, _ = run(monkeypatch, "eighty thousand instead", turn("refinement", PreferenceUpdate(add_hard_constraints={"budget_max": 80000})), state=state)
    assert not result.metadata.clarification_required and result.state.hard_constraints["budget_max"] == 80000


@pytest.mark.parametrize("error", [ProviderError("secret response", code="rate_limit"), TimeoutError("secret"), RuntimeError("raw secret")])
def test_primary_error_then_backup_once_without_sensitive_output(monkeypatch, capsys, error):
    result, first, second = run(monkeypatch, "Tìm ramen", error, turn(delta=PreferenceUpdate(set_values={"food": ["ramen"]})))
    assert result.state.food == ["ramen"] and result.metadata.fallback_used
    first.interpret_turn.assert_called_once(); second.interpret_turn.assert_called_once()
    assert len(result.metadata.provider_errors) == 1
    assert "secret" not in result.metadata.model_dump_json() + capsys.readouterr().out


def test_both_fail_atomic_rollback_including_form(monkeypatch):
    state = UserPreferenceState(session_id="S", food=["ramen"], hard_constraints={"budget_max": 100000})
    result, _, _ = run(monkeypatch, "Phở chay dưới 100k cách tôi 3km", TimeoutError(), TimeoutError(),
        state=state, form={"food": "pizza", "budget_max": 80000})
    assert result.metadata.clarification_required and result.metadata.intent == "clarification"
    assert result.state == state and not any(result.preference_update.model_dump().values())


def test_empty_browser_snapshot_does_not_make_an_empty_search_safe(monkeypatch):
    result, _, _ = run(monkeypatch, "Chào bạn", turn(), turn(), state=UserPreferenceState(session_id="S"))
    assert result.metadata.clarification_required and result.metadata.state_preserved


@pytest.mark.parametrize("message,delta", [
    ("Tôi muốn quán yên tĩnh hơn", PreferenceUpdate(set_values={"food": []})),
    ("Tôi muốn quán yên tĩnh hơn", PreferenceUpdate(add_hard_constraints={"quiet": True})),
])
def test_ambience_refinement_cannot_clear_food_or_invent_mandatory_quiet(monkeypatch, message, delta):
    state = UserPreferenceState(session_id="S", food=["ramen"])
    result, _, _ = run(monkeypatch, message, turn("refinement", delta), turn("refinement", delta), state=state)
    assert result.metadata.clarification_required and result.state == state


def test_existing_serving_category_and_beverage_switch_semantics(monkeypatch):
    state = UserPreferenceState(session_id="S", food=["ramen"])
    wet = PreferenceUpdate(set_values={"food": []}, add_hard_constraints={"item_kind": "food", "serving_style": ["broth", "soup"]})
    result, _, _ = run(monkeypatch, "Tìm món nước", turn(delta=wet), state=state)
    assert not result.metadata.clarification_required
    assert result.state.food == [] and result.state.hard_constraints == wet.add_hard_constraints
    beverage = PreferenceUpdate(set_values={"food": []}, add_hard_constraints={"item_kind": "beverage"}, remove_preferences=["hard_constraints.serving_style"])
    switched, _, _ = run(monkeypatch, "Đổi sang đồ uống", turn("refinement", beverage), state=result.state)
    assert not switched.metadata.clarification_required
    assert switched.state.hard_constraints == {"item_kind": "beverage"}


@pytest.mark.parametrize("message,delta", [
    ("Phở chay dưới 100k cách tôi 3km", PreferenceUpdate(add_hard_constraints={"max_distance_km": 30})),
    ("ramen dưới 100k", PreferenceUpdate(add_hard_constraints={"budget_max": 100})),
    ("ramen trong 15 phút", PreferenceUpdate(add_hard_constraints={"max_distance_km": 15})),
    ("ramen dưới 100k", PreferenceUpdate(add_hard_constraints={"parking": True})),
    ("ramen over 100k", PreferenceUpdate(add_hard_constraints={"budget_max": 100000})),
    ("ramen not within three kilometers", PreferenceUpdate(add_hard_constraints={"max_distance_km": 3})),
    ("I prefer air conditioning", PreferenceUpdate(add_hard_constraints={"air_conditioning": True})),
    ("not vegetarian pho", PreferenceUpdate(add_hard_constraints={"vegetarian": True})),
    ("Tìm phở", PreferenceUpdate(set_values={"location": {"lat": 10.77, "lon": 106.69}})),
    ("dị ứng sữa", PreferenceUpdate(add_hard_constraints={"allergens_excluded": ["peanut"]})),
    ("dị ứng một chất chưa rõ", PreferenceUpdate(add_hard_constraints={"allergens_excluded": ["milk"]})),
    ("Tìm ramen", PreferenceUpdate(references=[{"restaurant_id": "invented"}])),
])
def test_unsafe_or_unsupported_delta_rejected_with_state_rollback(monkeypatch, message, delta):
    result, _, _ = run(monkeypatch, message, turn(delta=delta), turn(delta=delta))
    assert result.metadata.clarification_required
    assert result.state == UserPreferenceState(session_id="S")


def test_positive_allergy_and_scoped_retraction_preserve_other_targets(monkeypatch):
    delta = PreferenceUpdate(add_hard_constraints={"allergens_excluded": ["milk", "peanut"]})
    first, _, _ = run(monkeypatch, "I am allergic to milk and peanuts", turn(delta=delta))
    assert first.state.hard_constraints["allergens_excluded"] == ["milk", "peanut"]
    second, _, _ = run(monkeypatch, "Không còn dị ứng sữa nữa", turn("refinement", PreferenceUpdate(remove_preferences=["hard_constraints.allergens_excluded"])), state=first.state)
    assert not second.metadata.clarification_required
    assert second.state.hard_constraints["allergens_excluded"] == ["peanut"]


def test_form_authority_overrides_provider_conflict(monkeypatch):
    delta = PreferenceUpdate(set_values={"food": ["pizza"], "location": {"lat": 1, "lon": 2}}, add_hard_constraints={"budget_max": 999000})
    result, _, _ = run(monkeypatch, "Tìm phở dưới 100k", turn(delta=delta),
        state=UserPreferenceState(session_id="S", hard_constraints={"budget_max": 150000}),
        form={"food": "ramen", "budget_max": 80000, "location": {"lat": 10.77, "lon": 106.69}})
    assert not result.metadata.clarification_required
    assert result.state.food == ["ramen"] and result.state.hard_constraints["budget_max"] == 80000
    assert result.state.location.lat == 10.77


def test_semantic_quote_supports_translated_food_and_context_without_lexical_rule(monkeypatch):
    delta = PreferenceUpdate(set_values={"food": ["phở chay"]}, context_updates={"meal_time": "dinner"})
    result, _, _ = run(monkeypatch, "vegetarian pho for my evening meal", turn(delta=delta,
        evidence=[("food", "vegetarian pho"), ("context.meal_time", "evening meal")]))
    assert not result.metadata.clarification_required and result.state.context == {"meal_time": "dinner"}


def test_fabricated_quote_is_rejected(monkeypatch):
    response = turn(delta=PreferenceUpdate(set_values={"food": ["phở"]}), evidence=[("food", "not in user input")])
    result, _, _ = run(monkeypatch, "Tìm ramen", response, response)
    assert result.metadata.clarification_required


def test_real_but_unrelated_quote_does_not_ground_invented_food(monkeypatch):
    response = turn(delta=PreferenceUpdate(set_values={"food": ["ramen"]}), evidence=[("food", "Chào bạn")])
    result, _, _ = run(monkeypatch, "Chào bạn", response, response)
    assert result.metadata.clarification_required and not result.state.food


def test_nonsearch_cannot_smuggle_mutation_or_catalog_claims(monkeypatch):
    bad = turn("conversation", PreferenceUpdate(set_values={"food": ["ramen"]}), reply="Chào bạn")
    claims = turn("informational", reply="Quán ABC đang mở cửa và có giá 50k.")
    result, _, _ = run(monkeypatch, "Chào bạn", bad, claims)
    assert result.metadata.clarification_required and not result.state.food


def test_word_number_prices_are_not_allowed_in_conversation(monkeypatch):
    claimed = turn("informational", reply="Một tô phở giá fifty thousand VND.")
    result, _, _ = run(monkeypatch, "Phở là gì?", claimed, claimed)
    assert result.metadata.clarification_required


def test_local_v4_is_last_fallback_with_same_safety_checks(monkeypatch):
    local = SimpleNamespace(parse=Mock(return_value=SLMParseResult(update=PreferenceUpdate(set_values={"food": ["ramen"]},
        add_hard_constraints={"budget_max": 150000, "max_distance_km": 3}), confidence=.8)))
    result, first, second = run(monkeypatch, "Tìm ramen dưới 150k trong 3km", TimeoutError(), TimeoutError(),
        config=ConversationConfig(llm_provider="openrouter_chain", local_slm_enabled=True), slm_provider=local)
    assert result.metadata.parser_used == "slm" and not result.metadata.clarification_required
    assert result.metadata.provider_models[-1] == "local/qwen-v4"
    first.interpret_turn.assert_called_once(); second.interpret_turn.assert_called_once(); local.parse.assert_called_once()
    assert local.parse.call_args.args[0].rule_result.update == PreferenceUpdate()


def test_primary_success_never_loads_local_and_missing_artifacts_are_safe(monkeypatch):
    local = SimpleNamespace(parse=Mock(side_effect=AssertionError("Do not load early")))
    result, _, _ = run(monkeypatch, "Tìm ramen", turn(delta=PreferenceUpdate(set_values={"food": ["ramen"]})),
        config=ConversationConfig(llm_provider="openrouter_chain", local_slm_enabled=True), slm_provider=local)
    assert not result.metadata.slm_called; local.parse.assert_not_called()
    monkeypatch.setattr("conversation.llm_first._local_available", lambda _: False)
    missing, _, _ = run(monkeypatch, "Tìm ramen", TimeoutError(), TimeoutError(),
        config=ConversationConfig(llm_provider="openrouter_chain", local_slm_enabled=True))
    assert missing.metadata.clarification_required and not missing.metadata.slm_called


def test_local_extractor_does_not_turn_a_question_into_a_search(monkeypatch):
    local = SimpleNamespace(parse=Mock(side_effect=AssertionError("Extraction LoRA is not a chat classifier")))
    result, _, _ = run(monkeypatch, "Phở khác bún như thế nào?", TimeoutError(), TimeoutError(),
        config=ConversationConfig(llm_provider="openrouter_chain", local_slm_enabled=True), slm_provider=local)
    assert result.metadata.clarification_required; local.parse.assert_not_called()


def test_optional_rule_fallback_runs_only_after_both_cloud_failures(monkeypatch):
    result, first, second = run(monkeypatch, "Tìm ramen dưới 150k trong 3km", TimeoutError(), TimeoutError(),
        config=ConversationConfig(llm_provider="openrouter_chain", rule_fallback_enabled=True))
    assert result.metadata.parser_used == "rule_fallback" and not result.metadata.clarification_required
    assert result.state.hard_constraints == {"budget_max": 150000, "max_distance_km": 3}
    first.interpret_turn.assert_called_once(); second.interpret_turn.assert_called_once()


def test_identity_fails_before_any_provider(monkeypatch):
    factory = Mock(side_effect=AssertionError("No provider for another session"))
    monkeypatch.setattr("conversation.llm_first.create_provider", factory)
    with pytest.raises(ValueError):
        process_user_request(UserRequest(session_id="S", current_state=UserPreferenceState(session_id="other")),
            config=ConversationConfig(llm_provider="openrouter_chain"))
    factory.assert_not_called()
