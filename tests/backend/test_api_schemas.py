import pytest
from pydantic import ValidationError

from backend.api.schemas import SearchRequest
from common.schemas import UserPreferenceState


def test_defaults_are_safe():
    request = SearchRequest()
    assert request.top_k == 10
    assert request.exclude_restaurant_ids == []


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        SearchRequest(mesage="typo")


@pytest.mark.parametrize("bad", [{"top_k": 0}, {"top_k": 51}, {"message": "x" * 501}])
def test_limits_are_enforced(bad):
    with pytest.raises(ValidationError):
        SearchRequest(**bad)


def test_to_command_carries_everything():
    request = SearchRequest(message="pho", exclude_restaurant_ids=["R1"], top_k=3)
    command = request.to_command("S1")
    assert command.session_id == "S1"
    assert command.message == "pho"
    assert list(command.exclude_restaurant_ids) == ["R1"]
    assert command.top_k == 3


def test_search_reuses_canonical_preference_state_contract():
    request = SearchRequest(preference_state={
        "session_id": "frontend", "food": ["phở"], "cuisine": ["Vietnamese"],
        "hard_constraints": {"budget_max": 150000}, "semantic_preferences": ["quiet"],
    })
    assert isinstance(request.preference_state, UserPreferenceState)
    assert request.to_command("cookie-id").preference_state is request.preference_state
    assert SearchRequest().preference_state is None


@pytest.mark.parametrize("constraints", [
    {"max_distance_km": -1}, {"budget_max": -100}, {"budget_max": "100k"},
    {"item_kind": "invalid"}, {"serving_style": []},
])
def test_snapshot_reuses_known_constraint_validation(constraints):
    with pytest.raises(ValidationError):
        SearchRequest(preference_state={"session_id": "frontend", "hard_constraints": constraints})
