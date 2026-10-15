"""Qwen V4 input preparation regressions; authored fixtures, offline providers."""

from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from common.schemas import Candidate, PreferenceUpdate, RankedResult, UserPreferenceState, UserRequest
from conversation.config import ConversationConfig
from conversation.normalization import normalize_update
from conversation.parser import parse_user_input, parse_user_input_detailed
from conversation.preprocessing import prepare_input
from conversation.providers.mock import MockProvider
from conversation.service import process_user_request
from conversation.state_manager import update_state
from pipeline import recommend


ENABLED = ConversationConfig(translation_enabled=True)


def translator(answer):
    return SimpleNamespace(translate=Mock(side_effect=answer) if callable(answer)
                           else Mock(return_value=answer))


@pytest.mark.parametrize("original,translated,expected", [
    ("Find a quiet restaurant under 100k", "tìm quán yên tĩnh dưới AI2KEEP0X",
     {"add_semantic_preferences": ["quiet"], "add_hard_constraints": {"budget_max": 100000}}),
    ("I'm allergic to peanuts", "dị ứng đậu phộng",
     {"add_hard_constraints": {"allergens_excluded": ["peanut"]}}),
    ("I'd prefer air conditioning", "ưu tiên có điều hòa",
     {"add_soft_preferences": {"air_conditioning": True}}),
    ("I don't like spicy food", "không thích cay", {"add_negative_preferences": ["spicy"]}),
    ("I don't like peanuts", "không thích đậu phộng", {"add_negative_preferences": ["peanut"]}),
    ("I must have air conditioning", "bắt buộc có điều hòa", {"add_hard_constraints": {"air_conditioning": True}}),
])
def test_english_examples_translate_before_rules(original, translated, expected):
    tr = translator(translated)
    provider, slm = MockProvider(), Mock()
    request = UserRequest(session_id="S", message=original)
    result = process_user_request(request, provider, config=ENABLED, translator=tr, slm_provider=slm)
    assert result.preference_update == PreferenceUpdate.model_validate(expected)
    assert result.metadata.original_message == request.message == original
    assert result.metadata.translation_attempted and result.metadata.translation_succeeded
    assert result.metadata.translation_error is None
    assert provider.call_count == 0 and not result.metadata.requires_llm
    slm.parse.assert_not_called()
    assert tr.translate.call_args.kwargs == {"source_language": "en", "target_language": "vi"}
    if "100k" in original:
        assert tr.translate.call_args.args == ("Find a quiet restaurant under AI2KEEP0X",)
        assert type(result.state.hard_constraints["budget_max"]) is int


@pytest.mark.parametrize("message", [
    "tìm quán yên tĩnh dưới 100k", "ramen", "sushi", "Ramen Sushi",
    "Find quán yên tĩnh under 100k", "Find a quiet quan under 100k", "quiet sushi",
    "Find a place cho minh", "sushi please", "AI2KEEP0X Find a quiet restaurant",
])
def test_vietnamese_short_entities_and_uncertain_mixed_language_skip_translation(message):
    tr = translator(lambda *a, **k: pytest.fail("Uncertain language was translated"))
    prepared = prepare_input(UserRequest(session_id="S", message=message), ENABLED, tr)
    assert not prepared.translation_attempted and not prepared.translation_succeeded
    assert prepared.message == message
    tr.translate.assert_not_called()


@pytest.mark.parametrize("message,after", [
    ("cho mik quán yên tĩn xíu", "cho mình quán yên tĩnh xíu"),
    ("mình mún ăn phở", "mình muốn ăn phở"),
    ("mún tìm quán yên tĩn", "muốn tìm quán yên tĩnh"),
    ('tìm quán "yên tĩn"', 'tìm quán "yên tĩn"'),
    ("ăn mún ở quán Mún", "ăn mún ở quán Mún"),
    ("tìm phỡ ở Quan Yen Tin", "tìm phỡ ở Quan Yen Tin"),
])
def test_typos_only_in_established_context(message, after):
    request = UserRequest(session_id="S", message=message)
    prepared = prepare_input(request, ConversationConfig())
    assert prepared.message == after and prepared.original_message == message
    assert prepared.input_normalized == (message != after)
    assert prepare_input(request, ConversationConfig(input_normalization_enabled=False)).message == message


def test_requested_typo_case_and_original_logging(tmp_path):
    original = "cho mik quán yên tĩn xíu"
    config = ConversationConfig(log_enabled=True, log_path=str(tmp_path / "log.jsonl"))
    provider = MockProvider()
    result = process_user_request(UserRequest(session_id="S", message=original), provider, config=config)
    assert result.preference_update == PreferenceUpdate(add_semantic_preferences=["quiet"])
    assert provider.call_count == 0
    row = json.loads((tmp_path / "log.jsonl").read_text(encoding="utf-8"))
    assert row["message"] == row["original_message"] == original
    assert row["parsed_message"] == "cho mình quán yên tĩnh xíu"


def test_named_typos_are_protected_by_supplied_results():
    request = UserRequest(session_id="S", message="cho mik quán yên tĩn xíu",
        previous_results=[{"rank": 1, "restaurant_id": "unchanged", "restaurant_name": "yên tĩn"}])
    prepared = prepare_input(request, ConversationConfig())
    assert prepared.message == "cho mình quán yên tĩn xíu"


@pytest.mark.parametrize("outcome,code", [
    (None, "translation_rejected"), ("", "translation_rejected"),
    ("Find a quiet restaurant under AI2KEEP0X", "translation_rejected"),
    ("tìm quán yên tĩnh dưới 100000", "translation_rejected"),
    ("tìm quán yên tĩnh dưới AI2KEEP0X đô la", "translation_rejected"),
    ("tìm quán yên tĩnh dưới AI2KEEP0X km", "translation_rejected"),
    ("tìm quán yên tĩnh dưới AI2KEEP0X và AI2KEEP0X", "translation_rejected"),
    (TimeoutError("private-key"), "translation_failed"),
])
def test_translation_failure_uses_original_request(outcome, code):
    tr = translator("")
    if isinstance(outcome, Exception):
        tr.translate.side_effect = outcome
    else:
        tr.translate.return_value = outcome
    original = "Find a quiet restaurant under 100k"
    callback = Mock(return_value=PreferenceUpdate())
    result = process_user_request(UserRequest(session_id="S", message=original),
        MockProvider(callback=callback), config=ENABLED, translator=tr)
    assert callback.call_args.kwargs["message"] == original
    assert result.metadata.translation_attempted and not result.metadata.translation_succeeded
    assert result.metadata.translation_error == code
    assert result.metadata.parsed_message == result.metadata.original_message == original
    assert "private-key" not in result.model_dump_json()


@pytest.mark.parametrize("original,bad_translation", [
    ("I'm allergic to peanuts", "không thích đậu phộng"),
    ("I'm allergic to peanuts", "dị ứng hải sản"),
    ("I don't like spicy food", "thích cay"),
    ("I don't like spicy food", "không thích yên tĩnh"),
    ("I'd prefer air conditioning", "bắt buộc có điều hòa"),
    ("I must have air conditioning", "ưu tiên có điều hòa"),
    ("I am not allergic to peanuts", "dị ứng đậu phộng"),
    ("Find something like the second restaurant but cheaper", "tìm quán giống quán thứ nhất nhưng rẻ hơn"),
    ("Find a quiet restaurant", "tìm quán yên tĩnh và sushi"),
])
def test_translation_cue_losses_are_rejected(original, bad_translation):
    prepared = prepare_input(UserRequest(session_id="S", message=original), ENABLED, translator(bad_translation))
    assert prepared.translation_attempted and not prepared.translation_succeeded
    assert prepared.translation_error == "translation_rejected" and prepared.message == original


def test_missing_translator_and_default_disabled():
    request = UserRequest(session_id="S", message="Find a quiet restaurant under 100k")
    tr = translator("unused")
    assert not prepare_input(request, ConversationConfig(), tr).translation_attempted
    tr.translate.assert_not_called()
    prepared = prepare_input(request, ENABLED)
    assert not prepared.translation_succeeded and not prepared.translation_attempted
    assert prepared.translation_error == "translator_unavailable" and prepared.message == request.message


@pytest.mark.parametrize("amount", ["100K", "$100", "USD 100"])
def test_uppercase_units_and_currency_prefixes_restore_verbatim(amount):
    request = UserRequest(session_id="S", message=f"Find a quiet restaurant under {amount}")
    tr = translator("tìm quán yên tĩnh dưới AI2KEEP0X")
    prepared = prepare_input(request, ENABLED, tr)
    assert prepared.translation_succeeded and prepared.message == f"tìm quán yên tĩnh dưới {amount}"
    assert tr.translate.call_args.args == ("Find a quiet restaurant under AI2KEEP0X",)


def test_translation_protects_named_entities_amounts_units_and_inputs():
    request = UserRequest(session_id="S", message='Find sushi at "Little Tokyo" within 2km under 100k',
        current_state=UserPreferenceState(session_id="S", food=["bánh xèo"], hard_constraints={"budget_max": 120000}),
        previous_results=[{"rank": 2, "restaurant_id": "R/02", "menu_item_id": "M:02", "restaurant_name": "Little Tokyo"}],
        form={"food": "phở", "budget_max": 90000})
    before = deepcopy(request.model_dump())
    tr = translator('tìm AI2KEEP0X ở AI2KEEP1X trong AI2KEEP2X dưới AI2KEEP3X')
    provider = MockProvider(callback=lambda **kw: PreferenceUpdate(set_values={"food": ["sushi"]}))
    result = process_user_request(request, provider, config=ENABLED, translator=tr)
    assert tr.translate.call_args.args == ('Find AI2KEEP0X at AI2KEEP1X within AI2KEEP2X under AI2KEEP3X',)
    assert result.metadata.translation_succeeded
    assert result.metadata.parsed_message == 'tìm sushi ở "Little Tokyo" trong 2km dưới 100k'
    assert result.state.food == ["phở"]
    assert result.state.hard_constraints == {"budget_max": 90000, "max_distance_km": 2.0}
    assert request.model_dump() == before


def test_english_reference_and_turn_relative_events_preserve_ids():
    request = UserRequest(session_id="S", message="Find something like the second restaurant but cheaper",
        current_state=UserPreferenceState(session_id="S", hard_constraints={"budget_max": 100000}),
        previous_results=[{"rank": 2, "restaurant_id": "R/02", "menu_item_id": "M:02"}])
    tr = translator("tìm quán giống quán thứ hai nhưng rẻ hơn")
    provider = MockProvider(callback=lambda **kw: PreferenceUpdate(references=[{"rank": 2, "similar_to": True}]))
    result = process_user_request(request, provider, config=ENABLED, translator=tr)
    assert result.metadata.translation_succeeded and provider.call_count == 1
    assert result.preference_update.relative_updates == {"budget": "decrease"}
    assert result.preference_update.references == [{"status": "resolved", "rank": 2,
        "restaurant_id": "R/02", "menu_item_id": "M:02", "mention": "quán thứ hai", "similar_to": "R/02"}]
    assert result.state.hard_constraints == {"budget_max": 100000}
    assert "relative_updates" not in result.state.context


@pytest.mark.parametrize("translate", [False, True])
def test_prepared_message_reaches_qwen_then_external_with_frozen_threshold(translate):
    message = "Find a quiet restaurant with nice atmosphere" if translate else "cho mik quán yên tĩn, có view lạ"
    expected = "tìm quán yên tĩnh với không gian đẹp" if translate else "cho mình quán yên tĩnh, có view lạ"
    tr = translator(expected)
    local = SimpleNamespace(parse=Mock(return_value={"update": {}, "confidence": .79}))
    callback = Mock(return_value=PreferenceUpdate())
    config = ConversationConfig(local_slm_enabled=True, translation_enabled=translate)
    result = process_user_request(UserRequest(session_id="S", message=message),
        MockProvider(callback=callback), config=config, slm_provider=local, translator=tr)
    assert config.local_slm_min_confidence == .80
    assert local.parse.call_args.args[0].message == callback.call_args.kwargs["message"] == expected
    assert result.metadata.slm_fallback and result.metadata.llm_called
    assert result.preference_update == PreferenceUpdate(add_semantic_preferences=["quiet"])


@pytest.mark.parametrize("replacement", [False, True])
def test_canonical_open_vocabulary_and_removals(replacement):
    data = {"semantic_preferences": ["yên tĩnh", "quiet atmosphere", "quiet", "ánh sáng dịu"],
            "negative_preferences": ["không thích cay", "spicy", "mùi khói"],
            "cuisine": ["món Nhật", "japanese", "Regional cuisine"],
            "food": ["phở", "bún bò", "bánh xèo", "Hủ tiếu Nam Vang"]}
    constraints = {"allergens_excluded": ["peanuts", "lạc", "unknown allergen"]}
    update = PreferenceUpdate(set_values={**data, **({"hard_constraints": constraints} if replacement else {})},
                              add_hard_constraints={} if replacement else constraints)
    before = update.model_dump()
    normalized = normalize_update(update)
    assert {k: v for k, v in normalized.set_values.items() if k != "hard_constraints"} == {**data, "semantic_preferences": ["quiet", "ánh sáng dịu"],
        "negative_preferences": ["spicy", "mùi khói"], "cuisine": ["japanese", "Regional cuisine"]}
    assert (normalized.set_values["hard_constraints"] if replacement else normalized.add_hard_constraints) == {
        "allergens_excluded": ["peanut", "unknown allergen"]}
    assert update.model_dump() == before
    state = update_state(None, normalized, "S")
    removed = update_state(state, PreferenceUpdate(remove_preferences=["quiet atmosphere", "không thích cay"]), "S")
    assert removed.semantic_preferences == ["ánh sáng dịu"] and removed.negative_preferences == ["mùi khói"]


@pytest.mark.parametrize("message,payload", [
    ("Find food under 100k", {"add_hard_constraints": {"budget_max": 100}}),
    ("Find food within 500 meters", {"add_hard_constraints": {"max_distance_km": 500}}),
    ("I don't like peanuts", {"add_hard_constraints": {"allergens_excluded": ["peanut"]}}),
    ("I am not allergic to peanuts", {"add_hard_constraints": {"allergens_excluded": ["peanut"]}}),
    ("I'd prefer air conditioning", {"add_hard_constraints": {"air_conditioning": True}}),
    ("I'd prefer air conditioning but must have parking", {"add_hard_constraints": {"air_conditioning": True}}),
])
def test_observable_model_contradictions_fall_back(message, payload):
    local = SimpleNamespace(parse=Mock(return_value={"update": payload, "confidence": .80}))
    provider = MockProvider(callback=lambda **kw: payload)
    result = process_user_request(UserRequest(session_id="S", message=message), provider,
        config=ConversationConfig(local_slm_enabled=True), slm_provider=local)
    assert result.metadata.slm_fallback and result.metadata.llm_error == "invalid_output"
    assert result.state.hard_constraints == {} and result.metadata.partial_result


@pytest.mark.parametrize("value", [100.0, "100k", True, -1])
def test_budget_requires_integer_vnd(value):
    with pytest.raises(ValidationError):
        PreferenceUpdate(add_hard_constraints={"budget_max": value})


def test_valid_meter_conversion_is_accepted_without_changing_schema():
    provider = MockProvider(callback=lambda **kw: PreferenceUpdate(add_hard_constraints={"max_distance_km": .5}))
    result = process_user_request(UserRequest(session_id="S", message="Find food within 500 meters"), provider,
                                  config=ConversationConfig())
    assert result.state.hard_constraints == {"max_distance_km": .5}
    assert not result.metadata.llm_error


def test_form_priority_survives_partial_slm_repair_with_conflicting_text_units():
    payload = {"add_semantic_preferences": ["quiet"], "context_updates": {"occasion": 42},
               "add_hard_constraints": {"budget_max": 100000}}
    local = SimpleNamespace(parse=Mock(return_value={"update": payload, "confidence": .8}))
    provider = MockProvider(callback=lambda **kw: PreferenceUpdate(context_updates={"occasion": "casual"}))
    request = UserRequest(session_id="S", message="dưới 100k, không gian lạ", form={"budget_max": 90000})
    result = process_user_request(request, provider, config=ConversationConfig(local_slm_enabled=True), slm_provider=local)
    assert result.state.hard_constraints == {"budget_max": 90000}
    assert result.state.semantic_preferences == ["quiet"] and result.state.context == {"occasion": "casual"}
    assert not result.metadata.llm_error


def test_unknown_lowercase_entity_and_changed_tokens_are_preserved_or_rejected():
    request = UserRequest(session_id="S", message="Find a quiet restaurant near moonlight under 100k")
    tr = translator("tìm quán yên tĩnh gần AI2KEEP0X dưới AI2KEEP1X")
    prepared = prepare_input(request, ENABLED, tr)
    assert prepared.translation_succeeded and prepared.message == "tìm quán yên tĩnh gần moonlight dưới 100k"
    assert tr.translate.call_args.args[0] == "Find a quiet restaurant near AI2KEEP0X under AI2KEEP1X"
    tr.translate.return_value = "tìm quán yên tĩnh gần AI2KEEP1X dưới AI2KEEP0X"
    assert prepare_input(request, ENABLED, tr).translation_error == "translation_rejected"


def test_multiple_allergy_clauses_remain_for_model_interpretation():
    provider = MockProvider(callback=lambda **kw: PreferenceUpdate(add_hard_constraints={"allergens_excluded": ["milk"]}))
    result = process_user_request(UserRequest(session_id="S", message="I am not allergic to peanuts but I am allergic to milk"),
                                  provider, config=ConversationConfig())
    assert result.state.hard_constraints == {"allergens_excluded": ["milk"]} and not result.metadata.llm_error


def test_current_context_aliases_normalize_on_copies_without_dropping_free_text():
    state = UserPreferenceState(session_id="S", context={"transport_mode": "on foot", "occasion": "casual", "custom_occasion": "chat",
        "meal_time": "late night", "custom": {"nested": "unchanged"}})
    before = state.model_dump()
    result = update_state(state, PreferenceUpdate(), "S")
    assert result.context == {**state.context, "transport_mode": "walking", "meal_time": "late_night"}
    assert state.model_dump() == before


def test_config_flags_from_environment(monkeypatch):
    assert ConversationConfig.from_env().input_normalization_enabled
    assert not ConversationConfig.from_env().translation_enabled
    monkeypatch.setenv("AI2_INPUT_NORMALIZATION_ENABLED", "false")
    monkeypatch.setenv("AI2_TRANSLATION_ENABLED", "true")
    assert not ConversationConfig.from_env().input_normalization_enabled
    assert ConversationConfig.from_env().translation_enabled
    assert not ConversationConfig.from_env().local_slm_enabled


def test_ai2_to_fake_retrieval_and_ranking():
    request = UserRequest(session_id="S", message="Find a quiet restaurant under 100k", form={"cuisine": "món Nhật"})
    candidate = Candidate(restaurant_id="source:R/01", menu_item_id="M:02", dish_id="D:03", price=90000)
    seen = []
    tr = translator("tìm quán yên tĩnh dưới AI2KEEP0X")

    def retrieve(state, top_k):
        assert isinstance(state, UserPreferenceState) and state.cuisine == ["japanese"]
        assert state.semantic_preferences == ["quiet"] and state.hard_constraints == {"budget_max": 100000}
        seen.append(state)
        return [candidate]

    def rank(state, candidates, top_k):
        assert state is seen[0] and candidates == [candidate]
        assert not hasattr(state, "message")
        return [RankedResult(restaurant_id=candidate.restaurant_id, menu_item_id=candidate.menu_item_id,
            dish_id=candidate.dish_id, rank=1, score=.5, reason_features={"synthetic": True})]

    response = recommend(request, parse_fn=lambda r: parse_user_input(r, config=ENABLED, translator=tr),
                         retrieve_fn=retrieve, rank_fn=rank)
    assert response.results[0].restaurant_id == "source:R/01"
    assert response.results[0].menu_item_id == "M:02" and response.results[0].dish_id == "D:03"
