"""Frozen cross-team serialization and validation boundaries."""

import json

import pytest
from pydantic import ValidationError

from common.constants import AI_INTERFACE_VERSION
from common.schemas import (
    Candidate, FeedbackEvent, PreferenceUpdate, RankedResult,
    RecommendationResponse, UserPreferenceState, UserRequest,
)


@pytest.mark.parametrize("model", [
    UserPreferenceState(session_id="S", context={"transport_mode": "walking"}),
    Candidate(restaurant_id="R", restaurant_features={"custom": [True, None, {"tag": "demo"}]}),
    RankedResult(restaurant_id="R", rank=1, score=-2.5, reason_features={"custom": 0.9}),
    FeedbackEvent(session_id="S", action="future_backend_action"),
    RecommendationResponse(session_id="S", state=UserPreferenceState(session_id="S"), results=[]),
])
def test_json_round_trip(model):
    encoded = model.model_dump_json()
    json.loads(encoded)
    assert type(model).model_validate_json(encoded) == model


@pytest.mark.parametrize("schema,payload", [
    (UserPreferenceState, {"session_id": ""}),
    (Candidate, {}),
    (Candidate, {"restaurant_id": "R", "distance_km": -1}),
    (Candidate, {"restaurant_id": "R", "price": -1}),
    (Candidate, {"restaurant_id": "R", "menu_item_id": ""}),
    (Candidate, {"restaurant_id": "R", "location": {"lat": 91, "lon": 0}}),
    (Candidate, {"restaurant_id": "R", "match_features": {"bad": object()}}),
    (Candidate, {"restaurant_id": "R", "restaurant_features": {"bad": float("nan")}}),
    (RankedResult, {"restaurant_id": "R", "rank": 0, "score": 1}),
    (RankedResult, {"restaurant_id": "R", "rank": 1, "score": float("inf")}),
    (RankedResult, {"restaurant_id": "R", "rank": 1, "score": 1, "rating": 6}),
    (FeedbackEvent, {"session_id": "S", "action": " "}),
    (FeedbackEvent, {"session_id": "S", "action": "click", "rank_position": 0}),
    (RecommendationResponse, {"session_id": "S", "state": {}, "results": []}),
    (RecommendationResponse, {"session_id": "S", "state": {"session_id": "S"}, "results": [{}]}),
])
def test_invalid_payload_rejected(schema, payload):
    with pytest.raises(ValidationError):
        schema.model_validate(payload)


def test_defaults_do_not_share_feature_containers():
    first, second = Candidate(restaurant_id="R1"), Candidate(restaurant_id="R2")
    first.match_features["x"] = 1
    first.restaurant_features["y"] = [2]
    assert second.match_features == second.restaurant_features == {}
    assert second.menu_item_id is second.dish_id is second.distance_km is second.price is None


def test_v02_delta_and_previous_results_remain_unchanged():
    assert AI_INTERFACE_VERSION == "0.2"
    assert set(PreferenceUpdate.model_fields) == {
        "set_values", "add_hard_constraints", "add_soft_preferences",
        "add_semantic_preferences", "add_negative_preferences", "context_updates",
        "remove_preferences", "references", "relative_updates",
    }
    request = UserRequest(session_id="S", previous_results=[{"rank": 1, "restaurant_id": "R"}])
    assert request.previous_results[0].restaurant_id == "R"
    assert PreferenceUpdate.model_validate({}).context_updates == {}


@pytest.mark.parametrize("replacement", [False, True])
def test_context_known_aliases_and_custom_values_remain_compatible(replacement):
    from conversation import update_state
    context = {"transport_mode": "on foot", "occasion": "casual", "meal_time": "late night", "custom": "spaceship",
               "companions": ["solo", "custom group"]}
    update = PreferenceUpdate(**({"set_values": {"context": context}} if replacement else {"context_updates": context}))
    state = update_state(None, update, "S")
    assert state.context == {**context, "transport_mode": "walking", "meal_time": "late_night", "companions": ["alone", "custom group"]}
    assert UserPreferenceState.model_validate_json(state.model_dump_json()) == state
    assert set(UserPreferenceState.model_fields) == {
        "session_id", "user_id", "location", "food", "cuisine", "hard_constraints", "soft_preferences",
        "semantic_preferences", "negative_preferences", "reference_restaurants", "context",
    }


def test_ai1_candidate_is_consumed_directly_by_ai3_callable():
    from common.interfaces import RankingModule

    candidate = Candidate(restaurant_id="source:R/01", menu_item_id="menu:053", dish_id="dish:018")

    def mock_rank(state: UserPreferenceState, candidates: list[Candidate], top_k: int = 10) -> list[RankedResult]:
        assert candidates[0] is candidate
        assert isinstance(state, UserPreferenceState)
        return [RankedResult(
            restaurant_id=c.restaurant_id, menu_item_id=c.menu_item_id, dish_id=c.dish_id,
            rank=i, score=0.5, reason_features={"synthetic": True},
        ) for i, c in enumerate(candidates[:top_k], 1)]

    ranker: RankingModule = mock_rank
    result = ranker(UserPreferenceState(session_id="S"), [candidate])[0]
    for field in ("restaurant_id", "menu_item_id", "dish_id"):
        assert getattr(result, field) == getattr(candidate, field)
