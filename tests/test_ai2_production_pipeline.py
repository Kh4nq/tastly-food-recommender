"""Legacy rules-first acceptance/fallback regressions. Providers are deterministic mocks."""
from contextlib import nullcontext
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from common.schemas import PreferenceUpdate, PreviousResult, UserPreferenceState, UserRequest
from conversation.config import ConversationConfig, create_chain_provider
from conversation.providers.base import ProviderError
from conversation.service import process_user_request
from scripts.benchmark_ai2_providers import empty_wire


def fake(result):
    return SimpleNamespace(name="openrouter", parse_preference=Mock(side_effect=result if isinstance(result, Exception) else None,
        return_value=None if isinstance(result, Exception) else result), last_usage={"input_tokens": 10, "output_tokens": 5},
        last_cost_usd=.001, last_attempts=1, close=Mock())


def run(monkeypatch, message, primary=None, backup=None, state=None, **kwargs):
    first, second = fake(primary or PreferenceUpdate()), fake(backup or PreferenceUpdate())
    monkeypatch.setattr("conversation.parser.create_provider", lambda _: first)
    monkeypatch.setattr("conversation.parser.create_chain_provider", lambda _, **__: second)
    config = ConversationConfig(llm_first_enabled=False, llm_provider="openrouter_chain", openrouter_enabled=True, openrouter_api_key="mock-secret")
    result = process_user_request(UserRequest(session_id="S", message=message, current_state=state, **kwargs), config=config)
    return result, first, second


@pytest.mark.parametrize("message,food", [("Tìm bún riêu chay, không dùng nước hầm xương.", "bún riêu chay"),
    ("Mình muốn bánh mì chay ăn sáng.", "bánh mì chay")])
def test_FD01_FD02_explicit_diet_and_full_food(monkeypatch, message, food):
    result, _, backup = run(monkeypatch, message, PreferenceUpdate(set_values={"food": [food.removesuffix(" chay")]}))
    assert result.state.food == [food] and result.state.hard_constraints["vegetarian"] is True
    assert not result.metadata.clarification_required and not backup.parse_preference.called


@pytest.mark.parametrize("message,target", [
    ("Mình dị ứng quả óc chó, nhưng ăn hạt điều bình thường.", "walnut"),
    ("Dị ứng hạt dẻ cười, không phải đậu phộng.", "pistachio")])
def test_AL01_AL05_correct_target_not_substitute(monkeypatch, message, target):
    state = UserPreferenceState(session_id="S", hard_constraints={"allergens_excluded": ["milk"]})
    result, first, backup = run(monkeypatch, message,
        PreferenceUpdate(add_hard_constraints={"allergens_excluded": ["peanut"]}),
        PreferenceUpdate(add_hard_constraints={"allergens_excluded": [target]}), state)
    assert result.state.hard_constraints["allergens_excluded"] == ["milk", target]
    assert not result.state.food and not result.metadata.clarification_required
    assert first.parse_preference.call_count == backup.parse_preference.call_count == 1
    assert result.metadata.fallback_used and result.metadata.provider_errors == ["invalid_output"]


def test_CN01_food_negation_correction(monkeypatch):
    result, first, backup = run(monkeypatch, "Không phải sushi, mình muốn ramen.",
        state=UserPreferenceState(session_id="S", food=["sushi"]))
    assert result.state.food == ["ramen"]
    assert first.parse_preference.call_count <= 1 and not backup.parse_preference.called


@pytest.mark.parametrize("message", [
    "Tôi từng dị ứng sữa, giờ bác sĩ bảo đã hết nên bỏ ràng buộc đó.",
    "Không còn dị ứng sữa nữa.", "Bỏ ràng buộc dị ứng sữa."])
def test_CN05_scoped_milk_removal_preserves_peanut_and_other_constraints(monkeypatch, message):
    state = UserPreferenceState(session_id="S", hard_constraints={"allergens_excluded": ["milk", "peanut"], "wifi": True, "budget_max": 100000})
    before = state.model_dump()
    result, _, _ = run(monkeypatch, message, PreferenceUpdate(remove_preferences=["hard_constraints.allergens_excluded"]), state=state)
    assert result.state.hard_constraints == {"allergens_excluded": ["peanut"], "wifi": True, "budget_max": 100000}
    assert not result.metadata.clarification_required and state.model_dump() == before
    assert not set(result.preference_update.remove_preferences) & {"allergens_excluded", "hard_constraints.allergens_excluded"}


@pytest.mark.parametrize("message", ["Bỏ dị ứng đi.", "Nếu không còn dị ứng sữa thì bỏ nó.", "Đừng bỏ dị ứng sữa.",
    "Không còn dị ứng sữa và đậu phộng nữa.", "Không xóa dị ứng sữa.", "Đừng gỡ dị ứng sữa."])
def test_ambiguous_or_negated_retraction_preserves_state_and_clarifies(monkeypatch, message):
    state = UserPreferenceState(session_id="S", food=["ramen"], hard_constraints={"allergens_excluded": ["milk", "peanut"]})
    result, first, backup = run(monkeypatch, message, state=state)
    assert result.state == state and result.metadata.clarification_required and result.metadata.state_preserved
    assert not first.parse_preference.called and not backup.parse_preference.called


def test_TR05_remove_time_bound_keep_transport(monkeypatch):
    state = UserPreferenceState(session_id="S", hard_constraints={"max_travel_time_min": 15, "allergens_excluded": ["peanut"]},
                                context={"transport_mode": "motorbike"})
    result, _, backup = run(monkeypatch, "Bỏ giới hạn thời gian đi, còn phương tiện vẫn là xe máy.",
        PreferenceUpdate(remove_preferences=["max_travel_time_min"]), state=state)
    assert "max_travel_time_min" not in result.state.hard_constraints
    assert result.state.context["transport_mode"] == "motorbike"
    assert result.state.hard_constraints["allergens_excluded"] == ["peanut"]
    assert not backup.parse_preference.called


@pytest.mark.parametrize("failure", [TimeoutError("mock-secret"), ProviderError("mock-secret"),
    ProviderError("mock-secret", code="invalid_output"), {"bogus": True}])
def test_primary_failure_calls_backup_once(monkeypatch, failure):
    result, first, backup = run(monkeypatch, "Tìm ramen và chỗ view đẹp", failure,
        PreferenceUpdate(set_values={"food": ["ramen"]}, add_semantic_preferences=["view đẹp"]))
    assert result.state.food == ["ramen"] and not result.metadata.clarification_required
    assert first.parse_preference.call_count == backup.parse_preference.call_count == 1
    assert result.metadata.provider_models == ["google/gemini-3.5-flash-lite", "openai/gpt-5.4-mini"]
    assert result.metadata.llm_error is None and result.metadata.provider_attempts == 2
    assert result.metadata.cost_usd == .002 and result.metadata.usage == {"input_tokens": 20, "output_tokens": 10}
    assert "mock-secret" not in result.metadata.model_dump_json()


def test_primary_success_never_calls_backup(monkeypatch):
    result, first, backup = run(monkeypatch, "Tìm ramen và view đẹp", PreferenceUpdate(set_values={"food": ["ramen"]}))
    assert result.state.food == ["ramen"] and first.parse_preference.call_count == 1
    backup.parse_preference.assert_not_called()


def test_both_providers_fail_roll_back_even_rule_partial_update(monkeypatch):
    state = UserPreferenceState(session_id="S", food=["sushi"], hard_constraints={"budget_max": 100000, "allergens_excluded": ["peanut"]})
    result, _, _ = run(monkeypatch, "Dưới 80k, view đẹp lạ", TimeoutError("secret"), ProviderError("secret"), state)
    assert result.state == state and result.state is not state
    assert result.metadata.state_preserved and result.metadata.clarification_required
    assert not any(result.preference_update.model_dump().values())


@pytest.mark.parametrize("bad", [PreferenceUpdate(add_hard_constraints={"allergens_excluded": ["peanut"]}),
    PreferenceUpdate(remove_preferences=["allergens_excluded"]), PreferenceUpdate(set_values={"food": ["pizza"]}),
    PreferenceUpdate(context_updates={"party_size": 8}), PreferenceUpdate(set_values={"cuisine": ["korean"]}),
    PreferenceUpdate(set_values={"location": {"lat": 10.8, "lon": 106.7}})])
def test_unsafe_semantic_updates_never_commit(monkeypatch, bad):
    state = UserPreferenceState(session_id="S", hard_constraints={"allergens_excluded": ["milk"], "wifi": True})
    result, first, backup = run(monkeypatch, "Tìm ramen, view đẹp", bad, bad, state)
    assert first.parse_preference.call_count == backup.parse_preference.call_count == 1
    assert result.state == state and result.metadata.clarification_required


def test_unknown_allergy_cannot_be_replaced_with_known_nut(monkeypatch):
    state = UserPreferenceState(session_id="S", hard_constraints={"allergens_excluded": ["milk"]})
    bad = PreferenceUpdate(add_hard_constraints={"allergens_excluded": ["peanut"]})
    result, _, _ = run(monkeypatch, "Dị ứng một loại hạt chưa rõ", bad, bad, state)
    assert result.state == state and result.metadata.clarification_required


def test_repeating_prior_allergen_does_not_resolve_new_unknown_allergy(monkeypatch):
    state = UserPreferenceState(session_id="S", hard_constraints={"allergens_excluded": ["milk"]})
    repeated = PreferenceUpdate(add_hard_constraints={"allergens_excluded": ["milk"]})
    result, primary, backup = run(monkeypatch, "Dị ứng một loại hạt chưa rõ", repeated, repeated, state)
    assert primary.parse_preference.called and backup.parse_preference.called
    assert result.state == state and result.metadata.clarification_required and result.metadata.state_preserved


@pytest.mark.parametrize("message", ["Ok, cảm ơn", "cảm ơn bạn", "thanks"])
def test_noop_preserves_state_without_any_provider(monkeypatch, message):
    state = UserPreferenceState(session_id="S", food=["ramen"], hard_constraints={"allergens_excluded": ["milk"]})
    result, first, backup = run(monkeypatch, message, state=state)
    assert result.state == state and not result.metadata.clarification_required
    first.parse_preference.assert_not_called(); backup.parse_preference.assert_not_called()


def test_references_relative_updates_and_caller_ids(monkeypatch):
    delta = PreferenceUpdate(references=[{"rank": 2, "mention": "quán số hai", "sentiment": "negative"}], relative_updates={"budget": "decrease"})
    result, _, _ = run(monkeypatch, "Không thích quán số hai, tìm rẻ hơn", delta,
        previous_results=[PreviousResult(rank=2, restaurant_id="real-id")])
    assert result.state.reference_restaurants[0]["restaurant_id"] == "real-id"
    assert result.state.reference_restaurants[0]["sentiment"] == "negative"
    assert result.preference_update.relative_updates == {"budget": "decrease"}
    assert "relative_updates" not in result.state.context


@pytest.mark.parametrize("backup", [False, True])
def test_real_chain_wire_profiles_without_network(monkeypatch, backup):
    sent = []
    model = "openai/gpt-5.4-mini" if backup else "google/gemini-3.5-flash-lite"
    body = json.dumps({"model": model, "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(empty_wire())}}]}).encode()
    def send(request, **kwargs):
        sent.append(json.loads(request.data))
        return nullcontext(SimpleNamespace(read=lambda _: body))
    monkeypatch.setattr("conversation.providers.openrouter_provider.urlopen", send)
    p = create_chain_provider(ConversationConfig(llm_first_enabled=False, llm_provider="openrouter_chain", openrouter_enabled=True, openrouter_api_key="mock-secret"), backup=backup)
    p.parse_preference(message="ramen", current_state=None, previous_results=[])
    payload = sent[0]
    assert payload["response_format"]["json_schema"]["strict"] and payload["max_tokens"] == 512
    assert payload["provider"] == {"require_parameters": True, "allow_fallbacks": False} and p.max_retries == 0
    if backup:
        assert "temperature" not in payload and payload["reasoning"] == {"effort": "none"}
    else:
        assert payload["temperature"] == 0 and payload["reasoning"] == {"enabled": True}


def test_backend_adapter_contract_unchanged(monkeypatch):
    from backend.adapters.ai2_conversation import Ai2ConversationAdapter
    result, _, _ = run(monkeypatch, "ramen")
    adapter = Ai2ConversationAdapter(process=lambda _: result)
    turn = adapter.process(UserRequest(session_id="S", message="ramen"))
    assert turn.state == result.state and turn.parser_used == result.metadata.parser_used
    assert turn.clarification_required == result.metadata.clarification_required


def test_transport_correction_does_not_restore_the_old_walking_mode(monkeypatch):
    state = UserPreferenceState(session_id="S", context={"transport_mode": "walking"})
    result, _, _ = run(monkeypatch, "Giữ giới hạn 10 phút, chuyển từ đi bộ sang xe máy.",
        PreferenceUpdate(context_updates={"transport_mode": "motorbike"}), state=state)
    assert result.state.context["transport_mode"] == "motorbike"


def test_negated_distance_cannot_replace_minutes(monkeypatch):
    result, first, backup = run(monkeypatch, "Tìm quán trong vòng 12 phút đi bộ, không phải trong 12 km.",
        PreferenceUpdate(add_hard_constraints={"max_distance_km": 12}),
        PreferenceUpdate(add_hard_constraints={"max_travel_time_min": 12}, context_updates={"transport_mode": "walking"}))
    assert first.parse_preference.called and backup.parse_preference.called
    assert "max_distance_km" not in result.state.hard_constraints
    assert result.state.hard_constraints["max_travel_time_min"] == 12


def test_explicit_form_priority_survives_cloud_field_conflict(monkeypatch):
    result, _, backup = run(monkeypatch, "view đẹp", PreferenceUpdate(set_values={"food": ["pizza"]}),
        form={"food": "ramen", "budget_max": 80000})
    assert result.state.food == ["ramen"] and result.state.hard_constraints["budget_max"] == 80000
    backup.parse_preference.assert_not_called()


def test_cloud_mode_does_not_load_opt_in_local_before_primary(monkeypatch):
    primary = fake(PreferenceUpdate())
    monkeypatch.setattr("conversation.parser.create_provider", lambda _: primary)
    local = SimpleNamespace(parse=Mock(side_effect=AssertionError("Local must not be primary")))
    result = process_user_request(UserRequest(session_id="S", message="view đẹp"), config=ConversationConfig(llm_first_enabled=False, 
        llm_provider="openrouter_chain", local_slm_enabled=True), slm_provider=local)
    assert result.metadata.provider_models == ["google/gemini-3.5-flash-lite"]
    local.parse.assert_not_called()


def test_missing_negative_feedback_uses_backup(monkeypatch):
    delta = PreferenceUpdate(references=[{"rank": 1, "mention": "món số một", "sentiment": "negative"}])
    result, first, second = run(monkeypatch, "Món số một mình không thích.", PreferenceUpdate(), delta,
        previous_results=[PreviousResult(rank=1, restaurant_id="real")])
    assert first.parse_preference.called and second.parse_preference.called
    assert result.state.reference_restaurants[0]["sentiment"] == "negative"


def test_wrong_relative_direction_uses_backup_without_numeric_policy(monkeypatch):
    result, _, backup = run(monkeypatch, "Rẻ hơn, view đẹp nhé", PreferenceUpdate(relative_updates={"budget": "increase"}),
        PreferenceUpdate(relative_updates={"budget": "decrease"}))
    assert backup.parse_preference.called and result.preference_update.relative_updates == {"budget": "decrease"}
    assert not result.state.hard_constraints and "relative_updates" not in result.state.context


def test_scoped_retraction_does_not_silently_drop_same_turn_relative_event(monkeypatch):
    state = UserPreferenceState(session_id="S", hard_constraints={"allergens_excluded": ["milk", "peanut"], "budget_max": 100000})
    delta = PreferenceUpdate(remove_preferences=["allergens_excluded"], relative_updates={"budget": "decrease"})
    result, _, _ = run(monkeypatch, "Không còn dị ứng sữa, bỏ dị ứng sữa và tìm rẻ hơn.", delta, delta, state)
    assert result.state == state and result.metadata.clarification_required


def test_historical_allergy_without_current_confirmation_is_not_added(monkeypatch):
    result, first, second = run(monkeypatch, "Tôi từng dị ứng sữa, giờ đã hết.")
    assert not result.state.hard_constraints and result.metadata.clarification_required
    first.parse_preference.assert_not_called(); second.parse_preference.assert_not_called()


def test_last_allergy_can_be_retracted_without_removing_other_constraints(monkeypatch):
    state = UserPreferenceState(session_id="S", hard_constraints={"allergens_excluded": ["milk"], "wifi": True})
    result, _, _ = run(monkeypatch, "Không còn dị ứng sữa nữa.", state=state)
    assert result.state.hard_constraints == {"allergens_excluded": [], "wifi": True}
    assert not result.metadata.clarification_required


def test_chain_logging_redacts_secrets_and_unknown_cost_is_not_zero(monkeypatch, tmp_path):
    first, second = fake(ProviderError("mock-secret")), fake(PreferenceUpdate(set_values={"food": ["ramen"]}))
    first.last_cost_usd = None
    monkeypatch.setattr("conversation.parser.create_provider", lambda _: first)
    monkeypatch.setattr("conversation.parser.create_chain_provider", lambda _, **__: second)
    path = tmp_path / "turns.jsonl"
    config = ConversationConfig(llm_first_enabled=False, llm_provider="openrouter_chain", openrouter_api_key="mock-secret", log_enabled=True, log_path=str(path))
    result = process_user_request(UserRequest(session_id="S", message="Tìm ramen view đẹp mock-secret"), config=config)
    text = path.read_text(encoding="utf-8")
    assert "mock-secret" not in text and "mock-secret" not in repr(config)
    record = json.loads(text)
    assert record["provider_errors"] == ["provider_error"] and record["fallback_used"]
    assert result.metadata.cost_usd is None and not result.metadata.partial_result


def test_environment_selects_agreed_chain_without_auto_enable(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter_chain")
    config = ConversationConfig.from_env()
    assert config.openrouter_primary_model == "google/gemini-3.5-flash-lite"
    assert config.openrouter_backup_model == "openai/gpt-5.4-mini"
    assert not config.openrouter_enabled and not config.local_slm_enabled
    monkeypatch.setenv("OPENROUTER_PRIMARY_MODEL", "openrouter/auto")
    with pytest.raises(ValueError):
        ConversationConfig.from_env()


@pytest.mark.parametrize("message,wrong,correct", [
    ("Bắt buộc phải có Wi-Fi", PreferenceUpdate(add_hard_constraints={"wifi": False}), PreferenceUpdate(add_hard_constraints={"wifi": True})),
    ("Có Wi-Fi thì tốt", PreferenceUpdate(add_hard_constraints={"wifi": True}), PreferenceUpdate(add_soft_preferences={"wifi": True})),
    ("Chỉ bỏ yêu cầu Wi-Fi", PreferenceUpdate(add_hard_constraints={"wifi": False}), PreferenceUpdate(remove_preferences=["hard_constraints.wifi"])),
])
def test_wifi_strength_and_removal_preserve_allergy(monkeypatch, message, wrong, correct):
    state = UserPreferenceState(session_id="S", hard_constraints={"allergens_excluded": ["peanut"]})
    result, _, backup = run(monkeypatch, message, wrong, correct, state)
    assert backup.parse_preference.called and not result.metadata.clarification_required
    assert result.state.hard_constraints["allergens_excluded"] == ["peanut"]
    if correct.add_hard_constraints:
        assert result.state.hard_constraints["wifi"] is True
    else:
        assert "wifi" not in result.state.hard_constraints
