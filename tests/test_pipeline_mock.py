"""Integration through real AI 2 rules/state and injected AI 1/AI 3 fixtures."""

import pytest

from common.config import PipelineConfig
from common.schemas import Candidate, PreferenceUpdate, RankedResult, RecommendationResponse, UserPreferenceState, UserRequest
from conversation.config import ConversationConfig
from conversation.parser import parse_user_input_detailed
from pipeline import recommend


def rule_only(request):
    parsed = parse_user_input_detailed(request, config=ConversationConfig())
    assert not parsed.metadata.requires_llm
    assert not parsed.metadata.llm_called
    assert not parsed.metadata.slm_called
    return parsed.preference_update


@pytest.mark.parametrize("config,limits", [(None, (100, 10)), (PipelineConfig(retrieval_top_k=50, ranking_top_k=5), (50, 5))])
def test_end_to_end_typed_boundaries_and_ids(config, limits):
    request = UserRequest(session_id="S", user_id="U", message="Ăn ramen dưới 150k trong 3km")
    before = request.model_dump()
    seen = []
    candidate = Candidate(restaurant_id="R001", menu_item_id="M053", dish_id="D018", price=120000)

    def retrieve(state, top_k=100):
        assert isinstance(state, UserPreferenceState)
        assert not hasattr(state, "message")
        assert state.food == ["ramen"]
        assert state.hard_constraints["budget_max"] == 150000
        assert state.hard_constraints["max_distance_km"] == 3
        assert state.user_id == "U"
        assert top_k == limits[0]
        seen.append(state)
        return [candidate]

    def rank(state, candidates, top_k=10):
        assert state is seen[0]
        assert candidates[0] is candidate
        # Every bounded candidate is scored before restaurant-level Top-K.
        assert top_k == len(candidates)
        return [RankedResult(restaurant_id=candidate.restaurant_id, menu_item_id=candidate.menu_item_id,
                             dish_id=candidate.dish_id, rank=1, score=0.9, reason_features={"synthetic": True})]

    response = recommend(request, parse_fn=rule_only, retrieve_fn=retrieve, rank_fn=rank, config=config)
    assert isinstance(response, RecommendationResponse)
    assert response.session_id == response.state.session_id == "S"
    assert response.results[0].model_dump(include={"restaurant_id", "menu_item_id", "dish_id"}) == candidate.model_dump(include={"restaurant_id", "menu_item_id", "dish_id"})
    assert request.model_dump() == before
    assert RecommendationResponse.model_validate_json(response.model_dump_json()) == response


def test_followup_uses_real_ai2_state_without_replaying_relative_events():
    initial = UserPreferenceState(session_id="S", food=["ramen"], hard_constraints={"budget_max": 150000}, context={"meal_time": "dinner"})
    before = initial.model_dump()

    def parse(request):
        return PreferenceUpdate(context_updates={"transport_mode": "walking"}, remove_preferences=["hard_constraints.budget_max"], relative_updates={"distance": "decrease"})

    response = recommend(UserRequest(session_id="S", current_state=initial), parse_fn=parse,
                         retrieve_fn=lambda state, top_k: [], rank_fn=lambda state, candidates, top_k: [])
    assert response.results == []
    assert response.state.food == ["ramen"]
    assert response.state.hard_constraints == {}
    assert response.state.context == {"meal_time": "dinner", "transport_mode": "walking"}
    assert initial.model_dump() == before


@pytest.mark.parametrize("identity", ["session", "user"])
def test_identity_rejected_before_parsing(identity):
    current = UserPreferenceState(session_id="OTHER" if identity == "session" else "S", user_id="OTHER")
    def forbidden(request):
        pytest.fail("Parser must not run for inconsistent identity")
    with pytest.raises(ValueError, match="different"):
        recommend(UserRequest(session_id="S", user_id="U", current_state=current), parse_fn=forbidden)


def test_production_defaults_use_ai3_catboost_when_retrieval_is_injected():
    response = recommend(
        UserRequest(session_id="S"),
        parse_fn=lambda request: PreferenceUpdate(),
        retrieve_fn=lambda state, top_k: [Candidate(restaurant_id="R")],
    )
    assert [result.restaurant_id for result in response.results] == ["R"]
    assert response.results[0].reason_features["ranking_model"] == "catboost_yetirank"


def test_demo_is_rule_only_even_with_provider_and_slm_environment(monkeypatch):
    from examples.integration_demo import offline_parse, mock_retrieve_candidates, mock_rank_candidates
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LOCAL_SLM_ENABLED", "true")
    monkeypatch.setenv("LOCAL_SLM_MIN_CONFIDENCE", "invalid")
    response = recommend(UserRequest(session_id="S", message="Ăn ramen dưới 150k trong 3km"),
                         parse_fn=offline_parse, retrieve_fn=mock_retrieve_candidates, rank_fn=mock_rank_candidates)
    assert response.state.food == ["ramen"]
    assert response.results[0].reason_features["synthetic"] is True
