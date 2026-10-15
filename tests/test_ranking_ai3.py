from common.schemas import Candidate, UserPreferenceState
from ranking import rank_candidates
from ranking.evaluate import evaluate_ranking
from ranking.feature_builder import FEATURE_NAMES, build_feature_vector


def _state() -> UserPreferenceState:
    return UserPreferenceState(
        session_id="S",
        hard_constraints={"budget_max": 100_000, "max_distance_km": 5},
    )


def test_feature_order_and_derived_values():
    candidate = Candidate(
        restaurant_id="R1", price=50_000, distance_km=1,
        match_features={"category_match": 1.0},
    )
    values = build_feature_vector(_state(), candidate)
    assert len(FEATURE_NAMES) == 15
    assert values["price_ratio"] == 0.5
    assert values["budget_fit"] == 0.5
    assert values["distance_ratio"] == 0.2
    assert values["cuisine_match"] == 0.0
    assert values["food_match"] == 0.0
    assert values["semantic_similarity"] == 0.0


def test_catboost_artifact_feature_schema_matches_production():
    from catboost import CatBoostRanker

    model = CatBoostRanker()
    model.load_model("models/ranker/catboost_yetirank.cbm")
    assert model.feature_names_ == list(FEATURE_NAMES)


def test_rank_candidates_preserves_ids_and_uses_top_k():
    candidates = [
        Candidate(restaurant_id="R1", menu_item_id="M1", dish_id="D1", price=50_000, distance_km=1),
        Candidate(restaurant_id="R2", menu_item_id="M2", dish_id="D2", price=90_000, distance_km=4),
    ]
    results = rank_candidates(_state(), candidates, top_k=1)
    assert len(results) == 1
    assert results[0].rank == 1
    assert (results[0].restaurant_id, results[0].menu_item_id, results[0].dish_id) == ("R1", "M1", "D1")
    assert results[0].reason_features["ranking_model"] == "catboost_yetirank"


def test_custom_ranker_and_ties_are_deterministic():
    class FixedRanker:
        def score(self, state, candidates):
            return [1.0 for _ in candidates]

    candidates = [Candidate(restaurant_id="first"), Candidate(restaurant_id="second")]
    results = rank_candidates(_state(), candidates, ranker=FixedRanker())
    assert [result.restaurant_id for result in results] == ["first", "second"]
    assert results[0].reason_features["ranking_model"] == "catboost_yetirank"


def test_metrics_on_hand_computable_group():
    rows = [
        {"session_id": "S", "relevance": 3},
        {"session_id": "S", "relevance": 0},
    ]
    metrics = evaluate_ranking(rows, [2.0, 1.0])
    assert metrics["ndcg@5"] == 1.0
    assert metrics["ndcg@10"] == 1.0
    assert metrics["mrr"] == 1.0
    assert metrics["recall@5"] == 1.0


def test_ai3_derives_six_features_from_raw_metadata():
    state = UserPreferenceState(session_id='metadata', context={'meal_time': 'lunch'},
        soft_preferences={'preferred_category': 'noodle', 'preferred_protein': ['beef'],
                          'preferred_cooking_style': 'boiled', 'calorie_limit': 400})
    candidate = Candidate(restaurant_id='R', match_features={
        'primary_category': 'noodle', 'main_protein': 'beef', 'primary_cooking_style': 'boiled', 'calories': 600})
    values = build_feature_vector(state, candidate)
    assert list(values) == list(FEATURE_NAMES)
    assert values['category_match'] == values['protein_match'] == values['cooking_match'] == 1
    assert values['meal_category_score'] == .95
    assert values['calorie_ratio'] == 1.5 and values['calorie_fit'] == .5
    # Explicit numeric AI1 values retain compatibility, including zero.
    candidate.match_features['category_match'] = 0.0
    assert build_feature_vector(state, candidate)['category_match'] == 0


def test_unknown_metadata_and_invalid_calorie_limit_do_not_claim_fit():
    state = UserPreferenceState(session_id='unknown', context={'meal_time': 'late_night'},
                                soft_preferences={'preferred_category': 'unknown', 'calorie_limit': -1})
    candidate = Candidate(restaurant_id='R', match_features={'primary_category': 'unknown', 'calories': 400})
    values = build_feature_vector(state, candidate)
    assert all(values[k] == 0 for k in ('category_match', 'protein_match', 'cooking_match',
                                       'meal_category_score', 'calorie_fit', 'calorie_ratio'))


def test_ranking_preserves_preference_uncertainty_for_http_warnings():
    evidence = {'matched': [], 'unknown': ['quiet'], 'mismatched': [], 'unresolved_negative': ['smoke']}
    candidate = Candidate(restaurant_id='R', match_features={'preference_evidence': evidence})
    assert rank_candidates(_state(), [candidate])[0].reason_features['preference_evidence'] == evidence


def test_demo_ranking_remains_explicitly_labeled():
    candidate = Candidate(restaurant_id='R', restaurant_features={'demo_only': True})
    result = rank_candidates(_state(), [candidate])[0]
    assert result.reason_features['demo_only'] is True
