# AI 3 — Ranking + Evaluation

Current web assembly: [restaurant grouping and Top-K](RESTAURANT_RECOMMENDATION_FINAL.md).
CatBoost still scores individual bounded candidates. Grouping happens afterward;
representative scores stay unchanged and original candidate ranks are retained.
AI1 neutralizes restaurant-name-contaminated embedding similarity for the
synthetic catalog; the 15-feature order and trained model are unchanged.

## Ownership

Own `src/ranking/`, `models/ranker/`, `models/metadata/`, `notebooks/ai3/`, this
document and ranking tests. Coordinate common schemas with AI 1/AI 2/backend.

## Input schemas

`UserPreferenceState` and `list[Candidate]` from `common.schemas`, top_k=10.
Do not parse natural-language prompts, retrieve candidates or remap source IDs.

## RankedResult output

Return rank, finite score, reason_features and the candidate's unchanged
restaurant_id/menu_item_id/dish_id. Optional names/price/distance/rating retain
source meaning. Return ranks 1..N in order, at most top_k results. See
[integration contract](integration_contract.md). Internal models may change
without changing this envelope.

## Feature builder

`feature_builder.py` implements the notebook feature order:
`distance_km`, `price_ratio`, `budget_fit`, `distance_ratio`, `category_match`,
`protein_match`, `cooking_match`, `cuisine_match`, `meal_category_score`,
`calorie_fit`, `calorie_ratio`, `food_match`, `semantic_similarity`,
`dish_similarity`, `restaurant_similarity`. AI1 supplies distance and the four
food/similarity signals; AI3 derives budget/distance ratios and literal dish-cuisine
matches when absent. Unknown numeric values use `0.0`. See the
[integration audit](ai1_ai3_integration.md) for all 15 features, missing metadata,
CPU query configuration and offline integration tests.

## Weighted baseline

`baseline_ranker.py` implements the notebook weighted heuristic. Scores are not
probabilities, and stable input order resolves ties. This is the required
pre-model reference for evaluation.

## Trained model

`model_ranker.py` provides the `CatBoostYetiRanker` adapter. The main model is
CatBoost `YetiRank` with the 15-feature notebook schema. Loading validates the
artifact's stored feature names and order before inference.

## Metrics

`evaluate.py` implements NDCG@K, MRR and Recall@K grouped by `session_id`.
Relevance labels, query groups, cutoffs and train/test splits must be documented
with each experiment. Report retrieval coverage separately from reranking quality.

## Training

`train.py` exposes explicit CatBoost YetiRank training. Training never runs
during import or normal CI; real runs must record dataset, feature and model
versions plus leakage controls.

## Inference

As of 12 October 2026, absent numeric category/protein/cooking features are
derived from explicit raw metadata and requested labels. Meal-category uses
the V3 training lookup; calorie fit/ratio use catalog serving calories and the
requested limit. Unknown metadata gives zero; known calories without a limit
use the training neutral 1/1 encoding. See [implementation details](AI1_FIX_12-10-26.md).
This changes inference feature construction, not the 15-feature layout or weights.
Preference evidence passes through reason_features for HTTP uncertainty warnings;
it does not add model inputs.

`from ranking import rank_candidates`; public function resides in `predict.py`.
It lazily loads `models/ranker/catboost_yetirank.cbm` by default, or the path in
`AI3_MODEL_PATH`. The weighted baseline is used only when no model artifact
exists; both paths return the same result envelope.

## Limitations

The current CatBoost artifact is trained outside this repository. Record its
feature version, dataset split and evaluation report alongside future artifacts.

## Tests

`tests/test_ranking_ai3.py` and `tests/test_ai1_ai3_integration.py` cover ranking
and integration behavior. Contract/import tests check envelopes and safe imports.
Run the guarded regression suite in [setup](setup.md) for shared changes.
The older tracked `restaurant-ranker-v3-catboost.cbm` has 11 features and is not
the current 15-feature runtime model; retain it pending AI3 provenance review.

## Definition of Done

`rank_candidates(state, candidates, top_k=10)` returns valid RankedResult objects
with rank, score and reason_features, preserving supplied IDs and returning <= 10
items in rank order. Evaluation provenance and limitations are documented; no
prompt parsing/data retrieval happens inside AI 3. Integration tests pass.
