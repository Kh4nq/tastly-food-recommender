"""Authored stability regressions; no benchmark data, SDKs or model loading."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from common.schemas import Candidate, PreferenceUpdate, RankedResult, UserPreferenceState, UserRequest
from conversation.config import ConversationConfig
from conversation.parser import parse_user_input_detailed
from conversation.preprocessing import prepare_input
from conversation.providers.mock import MockProvider
from conversation.reference_resolver import resolve_message_references
from conversation.rule_parser import parse_by_rules_detailed
from conversation.service import process_user_request
from pipeline import recommend


RESULTS = [{"rank": 2, "restaurant_id": "R/02", "menu_item_id": "M:02", "restaurant_name": "Sen"}]


@pytest.mark.parametrize("message,allergens", [
    ("Tránh đậu phộng vì dị ứng", ["peanut"]),
    ("Bị dị ứng hải sản", ["seafood"]),
    ("dị ứng đậu phộng, dị ứng hải sản", ["peanut", "seafood"]),
])
def test_clear_allergies_are_hard_without_narrowing(message, allergens):
    rule = parse_by_rules_detailed(message)
    assert rule.update.add_hard_constraints == {"allergens_excluded": allergens}
    result = process_user_request(UserRequest(session_id="S", message=message), config=ConversationConfig())
    assert result.state.hard_constraints == {"allergens_excluded": allergens}


@pytest.mark.parametrize("message", ["Không thích đậu phộng", "Không ăn hải sản", "không bị dị ứng hải sản",
                                     "không còn dị ứng đậu phộng", "không có dị ứng hải sản"])
def test_dislikes_nonconsumption_and_negation_do_not_invent_allergy(message):
    rule = parse_by_rules_detailed(message)
    assert "allergens_excluded" not in rule.update.add_hard_constraints
    provider = MockProvider(callback=lambda **kw: PreferenceUpdate())
    result = process_user_request(UserRequest(session_id="S", message=message), provider, config=ConversationConfig())
    assert not result.state.hard_constraints
    if message == "Không thích đậu phộng":
        assert result.state.negative_preferences == ["peanut"]


@pytest.mark.parametrize("removal", ["allergens_excluded", "hard_constraints.allergens_excluded"])
@pytest.mark.parametrize("route", ["slm", "external", "repair"])
def test_model_removal_cannot_erase_this_turn_explicit_allergy(route, removal):
    payload = PreferenceUpdate(remove_preferences=[removal], add_semantic_preferences=["ánh sáng dịu"])
    local_payload = payload.model_dump()
    if route == "repair":
        local_payload = {"add_semantic_preferences": ["quiet"], "context_updates": {"occasion": "chat"}}
    local = SimpleNamespace(parse=Mock(return_value={"update": local_payload, "confidence": .8}))
    provider = MockProvider(callback=lambda **kw: payload)
    request = UserRequest(session_id="S", message="dị ứng đậu phộng, không gian lạ",
        current_state=UserPreferenceState(session_id="S", hard_constraints={"allergens_excluded": ["milk"]}))
    result = process_user_request(request, provider, config=ConversationConfig(local_slm_enabled=route != "external"),
                                  slm_provider=local)
    assert result.state.hard_constraints["allergens_excluded"] == ["milk", "peanut"]
    assert removal not in result.preference_update.remove_preferences


def test_seafood_scope_survives_narrow_model_projection():
    provider = MockProvider(callback=lambda **kw: PreferenceUpdate(add_hard_constraints={"allergens_excluded": ["shellfish"]}))
    result = process_user_request(UserRequest(session_id="S", message="Bị dị ứng hải sản, muốn view lạ"), provider,
                                  config=ConversationConfig())
    assert "seafood" in result.state.hard_constraints["allergens_excluded"]


@pytest.mark.parametrize("replacement", [False, True])
def test_soft_allergen_output_cannot_be_silently_lost_beside_rule_hard_allergy(replacement):
    soft = {"allergens_excluded": ["milk"]}
    payload = {"set_values": {"soft_preferences": soft}} if replacement else {"add_soft_preferences": soft}
    local = SimpleNamespace(parse=Mock(return_value={"update": payload, "confidence": .8}))
    provider = MockProvider(callback=lambda **kw: PreferenceUpdate(add_hard_constraints={"allergens_excluded": ["milk"]}))
    # Retain unresolved ambience so the now-complete allergy rules still exercise
    # invalid local output and external fallback rather than bypassing inference.
    result = process_user_request(UserRequest(session_id="S", message="dị ứng đậu phộng và sữa, ánh sáng dịu"), provider,
        config=ConversationConfig(local_slm_enabled=True), slm_provider=local)
    assert result.metadata.slm_fallback and provider.call_count == 1
    assert result.state.hard_constraints == {"allergens_excluded": ["peanut", "milk"]}
    assert not result.state.soft_preferences


def test_model_cannot_turn_nonconsumption_into_allergy():
    local = SimpleNamespace(parse=Mock(return_value={"update": {"add_hard_constraints": {"allergens_excluded": ["shellfish"]}}, "confidence": .8}))
    provider = MockProvider(callback=lambda **kw: PreferenceUpdate())
    result = process_user_request(UserRequest(session_id="S", message="Không ăn hải sản"), provider,
        config=ConversationConfig(local_slm_enabled=True), slm_provider=local)
    assert result.metadata.slm_fallback and provider.call_count == 1
    assert not result.state.hard_constraints


@pytest.mark.parametrize("route", ["external", "slm"])
def test_unknown_allergy_cannot_be_accepted_as_an_empty_or_soft_update(route):
    payload = PreferenceUpdate(add_soft_preferences={"allergens_excluded": ["unknown ingredient"]})
    local = SimpleNamespace(parse=Mock(return_value={"update": {}, "confidence": .8}))
    request = UserRequest(session_id="S", message="Tôi bị dị ứng nguyên liệu chưa rõ")
    result = process_user_request(request, MockProvider(callback=lambda **kw: payload),
        config=ConversationConfig(local_slm_enabled=route == "slm"), slm_provider=local)
    assert result.metadata.partial_result and result.metadata.clarification_required
    assert not result.state.hard_constraints and not result.state.soft_preferences
    assert "dị ứng" in result.rule_result.unresolved_text and result.metadata.original_message == request.message


@pytest.mark.parametrize("message", ["có thể bị dị ứng đậu phộng", "nếu bị dị ứng hải sản", "chưa rõ bị dị ứng lạc"])
def test_uncertain_allergy_is_not_a_positive_rule_fact(message):
    rule = parse_by_rules_detailed(message)
    assert not rule.update.add_hard_constraints and rule.requires_llm
    result = process_user_request(UserRequest(session_id="S", message=message),
        MockProvider(callback=lambda **kw: PreferenceUpdate()), config=ConversationConfig())
    assert result.metadata.clarification_required and result.metadata.partial_result
    assert not result.state.hard_constraints and result.metadata.original_message == message


def test_unrequested_model_removal_cannot_clear_persistent_allergy():
    local = SimpleNamespace(parse=Mock(return_value={"update": {"remove_preferences": ["hard_constraints.allergens_excluded"]}, "confidence": .8}))
    provider = MockProvider(callback=lambda **kw: PreferenceUpdate(add_semantic_preferences=["ánh sáng dịu"]))
    state = UserPreferenceState(session_id="S", hard_constraints={"allergens_excluded": ["peanut"]})
    result = process_user_request(UserRequest(session_id="S", message="ánh sáng dịu", current_state=state), provider,
        config=ConversationConfig(local_slm_enabled=True), slm_provider=local)
    assert result.metadata.slm_fallback and result.state.hard_constraints == state.hard_constraints


@pytest.mark.parametrize("message,km", [("trong vòng 500m", .5), ("dưới 2km", 2), ("khoảng cách dưới 750m", .75)])
def test_distance_bounds_use_km(message, km):
    result = process_user_request(UserRequest(session_id="S", message=message), config=ConversationConfig())
    assert result.preference_update == PreferenceUpdate(add_hard_constraints={"max_distance_km": km})
    assert not result.metadata.llm_called


@pytest.mark.parametrize("message", ["nhóm 500 người", "dưới 2 phút", "ngân sách dưới 2m", "quán số 2", "món 500mystery"])
def test_non_distance_numbers_do_not_create_distance(message):
    assert "max_distance_km" not in parse_by_rules_detailed(message).update.add_hard_constraints


@pytest.mark.parametrize("message", ["nhóm 5 người, view lạ", "dưới 2 phút, view lạ", "dưới 100k, view lạ"])
def test_model_cannot_reuse_other_numeric_dimensions_as_distance(message):
    provider = MockProvider(callback=lambda **kw: PreferenceUpdate(add_hard_constraints={"max_distance_km": 2}))
    result = process_user_request(UserRequest(session_id="S", message=message), provider, config=ConversationConfig())
    assert result.metadata.llm_error == "invalid_output" and result.metadata.partial_result
    assert "max_distance_km" not in result.state.hard_constraints


def test_explicit_distance_form_keeps_priority_over_other_numeric_text():
    provider = MockProvider(callback=lambda **kw: PreferenceUpdate(add_hard_constraints={"max_distance_km": 2}))
    result = process_user_request(UserRequest(session_id="S", message="dưới 100k, view lạ", form={"max_distance_km": .5}),
                                  provider, config=ConversationConfig())
    assert result.state.hard_constraints == {"budget_max": 100000, "max_distance_km": .5}
    assert not result.metadata.llm_error


@pytest.mark.parametrize("message", ["ngân sách dưới 2m", "ngân sách thì dưới 2m"])
def test_budget_abbreviation_is_not_reinterpreted_as_meters(message):
    result = process_user_request(UserRequest(session_id="S", message=message),
        MockProvider(callback=lambda **kw: PreferenceUpdate(add_hard_constraints={"max_distance_km": .002})),
        config=ConversationConfig())
    assert result.metadata.llm_error == "invalid_output" and result.metadata.partial_result
    assert not result.state.hard_constraints


@pytest.mark.parametrize("replacement", [False, True])
@pytest.mark.parametrize("scope", ["hard_constraints", "soft_preferences"])
def test_unsupported_model_meter_field_falls_back(replacement, scope):
    payload = {"set_values": {scope: {"max_distance_m": 500}}} if replacement else {"add_" + scope: {"max_distance_m": 500}}
    local = SimpleNamespace(parse=Mock(return_value={"update": payload, "confidence": .8}))
    provider = MockProvider(callback=lambda **kw: PreferenceUpdate(add_semantic_preferences=["ánh sáng dịu"]))
    result = process_user_request(UserRequest(session_id="S", message="trong vòng 500m, không gian lạ"), provider,
        config=ConversationConfig(local_slm_enabled=True), slm_provider=local)
    assert result.metadata.slm_fallback and provider.call_count == 1
    assert result.state.hard_constraints == {"max_distance_km": .5}
    assert "max_distance_m" not in result.state.soft_preferences


@pytest.mark.parametrize("message", ["quán thứ hai", "cái số 2", "quán số 2 rẻ hơn", "giống quán thứ hai nhưng rẻ hơn"])
def test_reference_rank_only_uses_real_previous_results(message):
    refs = resolve_message_references(message, UserRequest(session_id="S", previous_results=RESULTS).previous_results)
    assert len(refs) == 1 and refs[0]["restaurant_id"] == "R/02" and refs[0]["menu_item_id"] == "M:02"
    parsed = parse_user_input_detailed(UserRequest(session_id="S", message=message, previous_results=RESULTS),
        MockProvider(callback=lambda **kw: PreferenceUpdate(references=[{"rank": 2, "similar_to": "giống" in message}])),
        config=ConversationConfig())
    assert len(parsed.preference_update.references) == 1
    if "rẻ hơn" in message:
        assert parsed.preference_update.relative_updates == {"budget": "decrease"}
        assert "budget_max" not in parsed.preference_update.add_hard_constraints


def test_duplicate_deterministic_mentions_resolve_to_one_object():
    request = UserRequest(session_id="S", message="quán thứ hai, quán Sen", previous_results=RESULTS)
    parsed = parse_user_input_detailed(request, MockProvider(callback=lambda **kw: PreferenceUpdate()), config=ConversationConfig())
    assert len(parsed.preference_update.references) == 1 and parsed.preference_update.references[0]["restaurant_id"] == "R/02"


@pytest.mark.parametrize("route", ["slm", "external"])
def test_cheaper_reference_cannot_create_absolute_budget(route):
    payload = PreferenceUpdate(add_hard_constraints={"budget_max": 80000})
    local = SimpleNamespace(parse=Mock(return_value={"update": payload, "confidence": .8}))
    provider = MockProvider(callback=lambda **kw: payload if route == "external" else PreferenceUpdate(
        references=[{"rank": 2, "similar_to": True}]))
    request = UserRequest(session_id="S", message="giống quán thứ hai nhưng rẻ hơn", previous_results=RESULTS,
        current_state=UserPreferenceState(session_id="S", hard_constraints={"budget_max": 100000}))
    result = process_user_request(request, provider, config=ConversationConfig(local_slm_enabled=route == "slm"),
                                  slm_provider=local)
    assert "budget_max" not in result.preference_update.add_hard_constraints
    assert result.preference_update.relative_updates == {"budget": "decrease"}
    assert result.state.hard_constraints == {"budget_max": 100000}
    assert len(result.preference_update.references) == 1 and result.preference_update.references[0]["restaurant_id"] == "R/02"


def test_budget_form_keeps_priority_over_cheaper_feedback():
    result = process_user_request(UserRequest(session_id="S", message="quán số 2 rẻ hơn", previous_results=RESULTS,
        form={"budget_max": 85000}), MockProvider(callback=lambda **kw: PreferenceUpdate(add_hard_constraints={"budget_max": 80000})),
        config=ConversationConfig())
    assert result.state.hard_constraints == {"budget_max": 85000}
    assert not result.preference_update.relative_updates and not result.metadata.llm_error


def test_missing_reference_stays_unresolved_without_fabricated_ids():
    parsed = parse_user_input_detailed(UserRequest(session_id="S", message="cái số 2"), config=ConversationConfig())
    assert parsed.preference_update.references == [{"status": "unresolved", "mention": "cái số 2"}]
    assert parsed.metadata.clarification_required


@pytest.mark.parametrize("message", ["đi xa hơn cũng được", "xa hơn cũng được"])
def test_distance_permission_is_not_a_requested_increase(message):
    assert not parse_by_rules_detailed(message).update.relative_updates
    local = SimpleNamespace(parse=Mock(return_value={"update": {"relative_updates": {"distance": "increase"}}, "confidence": .8}))
    provider = MockProvider(callback=lambda **kw: PreferenceUpdate())
    result = process_user_request(UserRequest(session_id="S", message=message,
        current_state=UserPreferenceState(session_id="S", hard_constraints={"max_distance_km": 2})), provider,
        config=ConversationConfig(local_slm_enabled=True), slm_provider=local)
    assert result.metadata.slm_fallback
    assert not result.preference_update.relative_updates and result.state.hard_constraints == {"max_distance_km": 2}


def test_ac_hard_and_older_companion_residue_survive_model_merge():
    request = UserRequest(session_id="S", message="Bắt buộc có máy lạnh, đi với người lớn tuổi")
    before = deepcopy(request.model_dump())

    def parse(data):
        assert data.message == request.message
        assert data.rule_result.update.add_hard_constraints == {"air_conditioning": True}
        assert "người lớn tuổi" in data.rule_result.unresolved_text
        return {"update": {"remove_preferences": ["hard_constraints.air_conditioning"],
                "add_soft_preferences": {"air_conditioning": True},
                "add_semantic_preferences": ["phù hợp người lớn tuổi"]}, "confidence": .8}

    result = process_user_request(request, config=ConversationConfig(local_slm_enabled=True),
                                  slm_provider=SimpleNamespace(parse=parse))
    assert result.state.hard_constraints == {"air_conditioning": True}
    assert not result.state.context and not result.state.soft_preferences
    assert result.state.semantic_preferences == ["phù hợp người lớn tuổi"]
    assert request.model_dump() == before


def test_soft_ac_cannot_be_promoted_when_other_residue_needs_model():
    result = process_user_request(UserRequest(session_id="S", message="ưu tiên có máy lạnh, đi với người lớn tuổi"),
        MockProvider(callback=lambda **kw: PreferenceUpdate(add_hard_constraints={"air_conditioning": True},
            add_semantic_preferences=["phù hợp người lớn tuổi"])), config=ConversationConfig())
    assert result.state.soft_preferences == {"air_conditioning": True} and not result.state.hard_constraints
    assert result.state.semantic_preferences == ["phù hợp người lớn tuổi"]


def test_meter_units_remain_literal_in_mock_translation():
    tr = SimpleNamespace(translate=Mock(return_value="Tìm món ăn trong AI2KEEP0X"))
    prepared = prepare_input(UserRequest(session_id="S", message="Find food within 500m"),
                             ConversationConfig(translation_enabled=True), tr)
    assert tr.translate.call_args.args == ("Find food within AI2KEEP0X",)
    assert prepared.translation_succeeded and prepared.message == "Tìm món ăn trong 500m"


def test_stable_update_crosses_injected_ai1_ai3_contracts():
    request = UserRequest(session_id="S", message="Tránh đậu phộng vì dị ứng, trong vòng 500m",
                          form={"food": "phở", "cuisine": "Nhật", "location": {"lat": 10.77, "lon": 106.69}})
    before = deepcopy(request.model_dump())
    candidate = Candidate(restaurant_id="R/02", menu_item_id="M:02", dish_id="D:02", distance_km=.25)
    seen = []

    def parse(req):
        parsed = parse_user_input_detailed(req, config=ConversationConfig())
        assert not parsed.metadata.llm_called and not parsed.metadata.slm_called
        return parsed.preference_update

    def retrieve(state, top_k):
        assert isinstance(state, UserPreferenceState) and not hasattr(state, "message")
        assert state.hard_constraints == {"allergens_excluded": ["peanut"], "max_distance_km": .5}
        assert state.cuisine == ["japanese"] and state.food == ["phở"]
        seen.append(state)
        return [candidate]  # Explicit synthetic fixture; no allergen filtering claim.

    def rank(state, candidates, top_k):
        assert state is seen[0] and candidates == [candidate]
        return [RankedResult(restaurant_id=candidate.restaurant_id, menu_item_id=candidate.menu_item_id,
            dish_id=candidate.dish_id, rank=1, score=.5, reason_features={"synthetic": True})]

    response = recommend(request, parse_fn=parse, retrieve_fn=retrieve, rank_fn=rank)
    assert response.results[0].model_dump(include={"restaurant_id", "menu_item_id", "dish_id"}) == candidate.model_dump(
        include={"restaurant_id", "menu_item_id", "dish_id"})
    assert request.model_dump() == before
