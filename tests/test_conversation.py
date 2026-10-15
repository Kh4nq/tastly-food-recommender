"""Contract, rule fixtures, state transitions, and an end-to-end demo."""

from copy import deepcopy
import json
from pathlib import Path
import unicodedata

import pytest
from pydantic import ValidationError

from common.schemas import Location, PreferenceUpdate, UserFormInput, UserPreferenceState, UserRequest
from conversation import parse_by_rules, parse_user_input, update_state
from conversation.providers import MockProvider

CASES = json.loads((Path(__file__).parent / "data" / "conversation_cases.json").read_text(encoding="utf-8"))
# The frozen historical fixture encoded distance permission as an increase.
# Current policy keeps that intent unresolved, without relabelling the file.
CURRENT_POLICY_EXPECTATIONS = {
    "distance-further": {}, "distance-travel": {},
    "relative-both-permissive": {"relative_updates": {"budget": "increase"}},
}


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_conversation_dataset(case: dict) -> None:
    request = UserRequest(session_id="S001", form=case.get("form", {}), message=case["message"],
                          previous_results=case.get("previous_results", []))
    provider = (MockProvider({case["message"]: PreferenceUpdate.model_validate(case["mock_response"])})
                if "mock_response" in case else None)
    update = parse_user_input(request, provider)
    # Compare all fields, including defaults, to catch unintended extractions.
    expected = CURRENT_POLICY_EXPECTATIONS.get(case["id"], case["expected"])
    assert update == PreferenceUpdate.model_validate(expected)
    if "form" not in case and case["message"] is not None:
        assert parse_by_rules(case["message"]) == PreferenceUpdate.model_validate(
            CURRENT_POLICY_EXPECTATIONS.get(case["id"], case.get("expected_rule", case["expected"])))


@pytest.mark.parametrize("schema,payload", [
    (Location, {"lat": 91, "lon": 0}),
    (Location, {"lat": 0, "lon": -181}),
    (Location, {"lat": float("nan"), "lon": 0}),
    (UserFormInput, {"budget_max": -1}),
    (UserFormInput, {"budget_max": 1.5}),
    (UserFormInput, {"max_distance_km": 0}),
    (UserFormInput, {"max_distance_km": float("inf")}),
    (UserFormInput, {"budegt_max": 100}),
    (UserRequest, {"session_id": ""}),
    (UserPreferenceState, {"session_id": "S", "food": "ramen"}),
    (PreferenceUpdate, {"set_values": {"unknown_field": 1}}),
    (PreferenceUpdate, {"relative_updates": {"budget": "double"}}),
    (PreferenceUpdate, {"references": [object()]}),
])
def test_schema_validation(schema: type, payload: dict) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate(payload)


def test_defaults_and_mutable_containers_are_independent() -> None:
    first = UserPreferenceState(session_id="A")
    second = UserPreferenceState(session_id="B")
    first.hard_constraints["vegetarian"] = True
    assert second.hard_constraints == {}
    a, b = PreferenceUpdate(), PreferenceUpdate()
    a.add_negative_preferences.append("spicy")
    assert b.add_negative_preferences == []
    assert UserRequest(session_id="S").form == UserFormInput()


def test_state_initialization() -> None:
    state = update_state(None, PreferenceUpdate(), "S001", "U001")
    assert state == UserPreferenceState(session_id="S001", user_id="U001")


def test_state_update_and_no_input_aliasing() -> None:
    current = UserPreferenceState(
        session_id="S", user_id="U", food=["phở"], cuisine=["vietnamese"],
        hard_constraints={"budget_max": 100000, "vegetarian": True},
        soft_preferences={"occasion": "friends"},
        context={"history": [{"turn": 1}]},
    )
    update = PreferenceUpdate(
        set_values={"food": ["ramen"], "location": {"lat": 10.77, "lon": 106.69}},
        add_hard_constraints={"budget_max": 150000},
        add_soft_preferences={"seating": {"type": "outdoor"}},
        add_semantic_preferences=["beautiful ambience"],
        add_negative_preferences=["spicy"], references=[{"id": "R1"}],
    )
    before_current, before_update = current.model_dump(), update.model_dump()
    state = update_state(current, update, "S")
    assert state.food == ["ramen"]
    assert state.cuisine == ["vietnamese"]
    assert state.user_id == "U"
    assert state.hard_constraints == {"budget_max": 150000, "vegetarian": True}
    assert state.soft_preferences == {"occasion": "friends", "seating": {"type": "outdoor"}}
    assert state.location == Location(lat=10.77, lon=106.69)
    assert state.semantic_preferences == ["beautiful ambience"]
    assert state.negative_preferences == ["spicy"]
    state.context["history"][0]["turn"] = 99
    state.soft_preferences["seating"]["type"] = "indoor"
    state.reference_restaurants[0]["id"] = "R2"
    assert current.model_dump() == before_current
    assert update.model_dump() == before_update


def test_removal_wins_and_unknown_removal_is_safe() -> None:
    current = UserPreferenceState(
        session_id="S", hard_constraints={"budget_max": 150000, "vegetarian": True},
        soft_preferences={"occasion": "friends"}, semantic_preferences=["quiet", "chill"],
        negative_preferences=["spicy"],
    )
    state = update_state(current, PreferenceUpdate(
        add_semantic_preferences=["quiet"],
        remove_preferences=["quiet", "spicy", "occasion", "budget_max", "unknown"],
    ), "S")
    assert state.semantic_preferences == ["relaxed ambience"]
    assert state.negative_preferences == []
    assert state.soft_preferences == {}
    assert state.hard_constraints == {"vegetarian": True}
    assert current.negative_preferences == ["spicy"]


def test_duplicate_prevention_and_reference_merging() -> None:
    update = PreferenceUpdate(
        add_semantic_preferences=["quiet", "quiet"],
        add_negative_preferences=["spicy", "spicy"],
        references=[{"id": "R1"}, {"id": "R1"}, "R2"],
    )
    state = update_state(None, update, "S")
    repeated = update_state(state, update, "S")
    assert repeated == state
    assert state.semantic_preferences == ["quiet"]
    assert state.negative_preferences == ["spicy"]
    assert state.reference_restaurants == [{"id": "R1"}, "R2"]


@pytest.mark.parametrize("initial", [{}, {"budget_max": 150000, "max_distance_km": 3}])
def test_relative_updates_never_invent_absolute_values(initial: dict) -> None:
    current = UserPreferenceState(session_id="S", hard_constraints=initial)
    state = update_state(current, parse_by_rules("Đắt thêm chút cũng được, gần hơn đi"), "S")
    assert state.hard_constraints == initial
    assert state.context == {}
    assert current.context == {}


def test_relative_events_do_not_persist_across_turns() -> None:
    state = update_state(None, parse_by_rules("rẻ hơn, gần hơn"), "S")
    state = update_state(state, parse_by_rules("mắc hơn cũng được"), "S")
    assert "relative_updates" not in state.context
    state = update_state(state, parse_by_rules("budget 200k"), "S")
    assert "relative_updates" not in state.context
    state = update_state(state, PreferenceUpdate(remove_preferences=["max_distance_km"]), "S")
    assert "relative_updates" not in state.context


def test_absolute_wins_over_relative_in_same_message() -> None:
    state = update_state(None, parse_by_rules("budget 150k, đắt thêm chút cũng được"), "S")
    assert state.hard_constraints["budget_max"] == 150000
    assert "relative_updates" not in state.context


def test_form_list_empty_and_zero_values_are_explicit() -> None:
    request = UserRequest(session_id="S", form=UserFormInput(
        food=[], cuisine=["japanese", "japanese"], budget_max=0,
    ), message="ramen dưới 100k")
    update = parse_user_input(request)
    assert update.set_values == {"food": [], "cuisine": ["japanese"]}
    assert update.add_hard_constraints == {"budget_max": 0}


def test_form_and_request_are_not_mutated_or_aliased() -> None:
    request = UserRequest(session_id="S", form={"food": ["sushi"], "location": {"lat": 0, "lon": 0}},
                          current_state=UserPreferenceState(session_id="S", food=["phở"]))
    before = deepcopy(request.model_dump())
    update = parse_user_input(request)
    update.set_values["food"].append("ramen")
    update.set_values["location"]["lat"] = 1
    assert request.model_dump() == before


def test_unicode_and_whitespace_normalization() -> None:
    text = unicodedata.normalize("NFD", "PHỞ dưới 150 NGHÌN")
    assert parse_by_rules(text.replace(" ", "  \n")) == PreferenceUpdate(
        set_values={"food": ["phở"]}, add_hard_constraints={"budget_max": 150000},
    )


def test_last_mention_wins() -> None:
    update = parse_by_rules("budget 200k, budget 100k; gần hơn, xa hơn cũng được; rẻ hơn, mắc hơn cũng được")
    assert update.add_hard_constraints == {"budget_max": 100000}
    # Permission to go farther does not replace the preceding closer request.
    assert update.relative_updates == {"distance": "decrease"}


@pytest.mark.parametrize("message", ["budget -100k", "dưới 2km", "budget 150kg", "budget 150kabc"])
def test_invalid_or_ambiguous_money_is_not_a_budget(message: str) -> None:
    assert "budget_max" not in parse_by_rules(message).add_hard_constraints


@pytest.mark.parametrize("message", ["không muốn gần hơn", "không muốn món chay", "không thích chỗ chill"])
def test_negated_positive_rules_are_not_applied(message: str) -> None:
    assert parse_by_rules(message) == PreferenceUpdate()


@pytest.mark.parametrize("session_id,user_id", [("other", "U"), ("S", "other")])
def test_identity_mismatch_is_rejected(session_id: str, user_id: str) -> None:
    with pytest.raises(ValueError, match="different"):
        update_state(UserPreferenceState(session_id="S", user_id="U"), PreferenceUpdate(), session_id, user_id)


def test_anonymous_state_can_acquire_user_id() -> None:
    state = update_state(UserPreferenceState(session_id="S"), PreferenceUpdate(), "S", "U")
    assert state.user_id == "U"


def test_invalid_replacement_fails_without_mutation() -> None:
    current = UserPreferenceState(session_id="S", food=["phở"])
    with pytest.raises(ValidationError):
        update_state(current, PreferenceUpdate(set_values={"food": 123}), "S")
    assert current.food == ["phở"]


def test_legacy_relative_context_is_purged() -> None:
    state = update_state(UserPreferenceState(session_id="S", context={"relative_updates": "bad"}), PreferenceUpdate(), "S")
    assert "relative_updates" not in state.context


def test_demo_flow_and_json_roundtrip() -> None:
    request = UserRequest.model_validate({
        "session_id": "S001", "user_id": "U001",
        "form": {"location": {"lat": 10.77, "lon": 106.69}},
        "message": "Tìm ramen dưới 150k trong vòng 3km, không ăn cay",
        "current_state": None,
    })
    update = parse_user_input(request)
    state = update_state(request.current_state, update, request.session_id, request.user_id)
    assert state == UserPreferenceState(
        session_id="S001", user_id="U001", location=Location(lat=10.77, lon=106.69),
        food=["ramen"], hard_constraints={"budget_max": 150000, "max_distance_km": 3},
        negative_preferences=["spicy"],
    )
    for value in (request, update, state):
        assert type(value).model_validate_json(value.model_dump_json()) == value
    next_request = UserRequest(session_id="S001", message="Xa quá, gần hơn đi", current_state=state)
    next_state = update_state(next_request.current_state, parse_user_input(next_request), next_request.session_id)
    assert next_state.hard_constraints == state.hard_constraints
    assert "relative_updates" not in next_state.context
