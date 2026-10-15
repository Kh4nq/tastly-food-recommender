"""Synthetic, offline AI1 -> AI3 compatibility; no production artifacts needed."""

from functools import partial
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from common.config import PipelineConfig
from common.schemas import Candidate, Location, RecommendationResponse, UserFormInput, UserPreferenceState, UserRequest
from conversation.config import ConversationConfig
from conversation.parser import parse_user_input_detailed
from pipeline import recommend
from ranking import rank_candidates
from ranking.feature_builder import FEATURE_NAMES, build_feature_matrix, build_feature_vector
from ranking.model_ranker import CatBoostYetiRanker
from retrieval.retriever import Retriever, retrieve_candidates


EXPECTED_FEATURES = (
    "distance_km", "price_ratio", "budget_fit", "distance_ratio",
    "category_match", "protein_match", "cooking_match", "cuisine_match",
    "meal_category_score", "calorie_fit", "calorie_ratio", "food_match",
    "semantic_similarity", "dish_similarity", "restaurant_similarity",
)


@pytest.fixture
def state():
    return UserPreferenceState(
        session_id="integration", location=Location(lat=10.77, lon=106.69),
        food=["Bún chay"], cuisine=["vietnamese"],
        hard_constraints={"budget_max": 100_000, "max_distance_km": 5},
    )


@pytest.fixture
def engine(monkeypatch, tmp_path):
    """Real retrieval code over in-memory tables and two-dimensional vectors."""
    from retrieval import embedder, hard_filter

    restaurants = pd.DataFrame([{
        "food_place_id": "test:restaurant:1", "name": "Synthetic test restaurant",
        "latitude": 10.77, "longitude": 106.69,
        "supported_cuisine": "vietnamese", "is_recommendable": True,
    }])
    dishes = pd.DataFrame([{
        "dish_id": "test:dish:1", "dish_name": "Bún chay",
        "supported_cuisine": "vietnamese", "is_vegetarian": True,
    }])
    menus = pd.DataFrame([{
        "menu_item_id": "test:menu:1", "food_place_id": "test:restaurant:1",
        "dish_id": "test:dish:1", "price_vnd": 50_000,
    }])
    monkeypatch.setattr(hard_filter, "load_tables", lambda path: (restaurants, dishes, menus))
    monkeypatch.setattr(embedder, "load_embeddings", lambda path: (
        np.array([[0.0, 1.0]], dtype=np.float32),
        pd.DataFrame([{"vector_row": 0, "food_place_id": "test:restaurant:1"}]),
        np.array([[1.0, 0.0]], dtype=np.float32),
        pd.DataFrame([{"vector_row": 0, "dish_id": "test:dish:1"}]),
        menus[["menu_item_id", "food_place_id", "dish_id"]],
        {"dataset_version": "v2-original-ids", "model": "test-query-model"},
    ))
    return Retriever(processed_dir=tmp_path)


def query_model():
    return SimpleNamespace(encode=Mock(return_value=np.array([[1.0, 0.0]], dtype=np.float32)))


def test_real_candidate_conversion_and_exact_feature_matrix(engine, state):
    engine.model = query_model()
    candidates = retrieve_candidates(state, retriever=engine)
    candidate = candidates[0]
    assert Candidate.model_validate_json(candidate.model_dump_json()) == candidate
    before = candidate.model_dump()
    state_before = state.model_dump()
    # Real hard filter, lexical match, cosine scoring, and Candidate conversion.
    assert candidate.match_features["dish_supported_cuisine"] == "vietnamese"
    assert candidate.match_features["is_vegetarian"] is True
    vector = build_feature_vector(state, candidate)
    assert FEATURE_NAMES == EXPECTED_FEATURES
    assert tuple(vector) == EXPECTED_FEATURES
    assert build_feature_matrix(state, candidates)[0] == pytest.approx([
        0.0, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0, 1.0,
        0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 0.0,
    ])
    assert candidate.model_dump() == before
    assert state.model_dump() == state_before


def test_numeric_derivations_and_missing_evidence(state):
    candidate = Candidate(restaurant_id="test:R", price=60_000, distance_km=2)
    vector = build_feature_vector(state, candidate)
    assert list(vector.values()) == pytest.approx([
        2.0, 0.6, 0.4, 0.4, *([0.0] * 11),
    ])
    assert list(build_feature_vector(state, Candidate(restaurant_id="test:unknown")).values()) == [0.0] * 15


@pytest.mark.parametrize("budget,price,expected", [
    (None, 50_000, (0.0, 0.0)), (0, 0, (0.0, 0.0)),
    (0, 50_000, (0.0, 0.0)), (100_000, None, (0.0, 0.0)),
    (100_000, 0, (0.0, 1.0)), (100_000, 120_000, (1.2, 0.0)),
])
def test_budget_fit_requires_evidence(budget, price, expected):
    state = UserPreferenceState(session_id="S", hard_constraints={} if budget is None else {"budget_max": budget})
    vector = build_feature_vector(state, Candidate(restaurant_id="test:R", price=price))
    assert (vector["price_ratio"], vector["budget_fit"]) == pytest.approx(expected)


@pytest.mark.parametrize("requested,evidence,expected", [
    (["vietnamese"], " Vietnamese ", 1.0),
    (["thai", "vietnamese"], "vietnamese", 1.0),
    (["Việt Nam"], "vietnamese", 0.0),  # No invented alias mapping.
    (["thai"], "vietnamese", 0.0), ([], "vietnamese", 0.0),
    (["unknown"], "unknown", 0.0), (["other"], "other", 0.0),
    (["vietnamese"], None, 0.0), (["vietnamese"], True, 0.0),
    (["vietnamese"], "thai;vietnamese", 0.0),
])
def test_cuisine_bridge_uses_only_explicit_dish_labels(requested, evidence, expected):
    state = UserPreferenceState(session_id="S", cuisine=requested)
    candidate = Candidate(
        restaurant_id="test:R", dish_name="Vietnamese dish",
        restaurant_features={"cuisine": "vietnamese"},
        match_features={"dish_supported_cuisine": evidence, "is_vegetarian": True},
    )
    assert build_feature_vector(state, candidate)["cuisine_match"] == expected


def test_explicit_numeric_features_keep_priority(state):
    supplied = {name: index / 20 for index, name in enumerate(EXPECTED_FEATURES)}
    candidate = Candidate(restaurant_id="test:R", price=90_000, distance_km=4,
                          match_features={**supplied, "dish_supported_cuisine": "vietnamese"})
    assert build_feature_vector(state, candidate) == supplied
    candidate.match_features = {"dish_supported_cuisine": "vietnamese"}
    candidate.restaurant_features = {"cuisine_match": 0.25}
    assert build_feature_vector(state, candidate)["cuisine_match"] == 0.25


def test_rank_candidates_uses_adapter_and_preserves_source_ids(engine, state):
    engine.model = query_model()
    candidates = retrieve_candidates(state, retriever=engine)
    candidates.append(Candidate(restaurant_id="test:unknown"))
    model = SimpleNamespace(predict=Mock(return_value=[0.8, 0.1]))
    results = rank_candidates(state, candidates, top_k=1, ranker=CatBoostYetiRanker(model))
    model.predict.assert_called_once_with(build_feature_matrix(state, candidates))
    assert len(results) == 1
    result = results[0]
    assert (result.restaurant_id, result.menu_item_id, result.dish_id) == (
        "test:restaurant:1", "test:menu:1", "test:dish:1",
    )
    assert (result.rank, result.score, result.price, result.distance_km) == (1, 0.8, 50_000, 0.0)
    assert result.reason_features["cuisine_match"] == 1.0


def test_pipeline_with_injected_retrieval_and_rank_functions(engine, state):
    engine.model = query_model()
    retrieve = Mock(side_effect=partial(retrieve_candidates, retriever=engine))
    model = SimpleNamespace(predict=Mock(return_value=[0.8]))
    rank = Mock(side_effect=partial(rank_candidates, ranker=CatBoostYetiRanker(model)))

    def offline_parse(request):
        parsed = parse_user_input_detailed(request, config=ConversationConfig())
        assert not parsed.metadata.llm_called and not parsed.metadata.slm_called
        return parsed.preference_update

    response = recommend(
        UserRequest(session_id=state.session_id, form=UserFormInput(
            location=state.location, food=state.food, cuisine=state.cuisine,
            budget_max=100_000, max_distance_km=5,
        )), parse_fn=offline_parse, retrieve_fn=retrieve, rank_fn=rank,
        config=PipelineConfig(retrieval_top_k=7, ranking_top_k=1),
    )
    retrieve.assert_called_once_with(response.state, top_k=7)
    assert rank.call_args.args[0] is response.state
    assert rank.call_args.kwargs == {"top_k": 1}
    assert response.results[0].menu_item_id == "test:menu:1"
    assert RecommendationResponse.model_validate_json(response.model_dump_json()) == response


@pytest.mark.parametrize("device,options", [(None, {}), ("", {}), (" cpu ", {"device": "cpu"})])
def test_query_device_configuration_is_lazy_and_offline(monkeypatch, engine, state, device, options):
    if device is None:
        monkeypatch.delenv("AI1_EMBEDDING_DEVICE", raising=False)
    else:
        monkeypatch.setenv("AI1_EMBEDDING_DEVICE", device)
    model = query_model()
    constructor = Mock(return_value=model)
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=constructor))
    assert engine.model is None
    retrieve_candidates(state, retriever=engine)
    retrieve_candidates(state, retriever=engine)
    constructor.assert_called_once_with("test-query-model", **options)
    assert model.encode.call_count == 2
    assert model.encode.call_args.kwargs == {"convert_to_numpy": True, "normalize_embeddings": True}


def test_cpu_setting_does_not_replace_injected_model_or_load_for_empty_query(monkeypatch, engine, state):
    monkeypatch.setenv("AI1_EMBEDDING_DEVICE", "cpu")
    constructor = Mock(side_effect=AssertionError("Unexpected model load"))
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=constructor))
    retrieve_candidates(UserPreferenceState(session_id="empty-query"), retriever=engine)
    engine.model = query_model()
    retrieve_candidates(state, retriever=engine)
    constructor.assert_not_called()
    engine.model.encode.assert_called_once()
