# AI1 -> AI3 integration audit

> Historical evidence: statuses and counts below describe that audit checkout.
> See [current setup](setup.md) and [artifact audit](artifact_audit.md) for current readiness.

> Update 12 October 2026: [the current implementation guide](AI1_FIX_12-10-26.md)
> documents the profile sidecar, metadata forwarding and six AI3 derivations.
> Tables below retain the historical audit; they do not describe today's fallback coverage.

The shared `Candidate` / `UserPreferenceState` schemas and public callable
interfaces already align. No schema, retrieval selection, CatBoost model or
training change is needed for this bridge. Source restaurant/menu/dish IDs stay
unchanged. Tests use synthetic in-memory tables, vectors and model predictions;
they do not measure retrieval coverage or ranking quality.

## Feature coverage (exact model order)

Explicit numeric features in `match_features`, then `restaurant_features`, retain
priority. The table describes the current AI1 output and AI3 fallbacks.

| # | Feature | Current source / fallback |
| --- | --- | --- |
| 1 | `distance_km` | AI1 top-level distance; AI3 uses it directly, or 0 if absent. |
| 2 | `price_ratio` | AI3: Candidate price / positive `budget_max`; otherwise 0. |
| 3 | `budget_fit` | AI3: max(0, 1 - price_ratio), requiring price/ratio evidence and a positive budget; otherwise 0. |
| 4 | `distance_ratio` | AI3: Candidate distance / `max_distance_km`; otherwise 0. |
| 5 | `category_match` | Not emitted by AI1; 0. |
| 6 | `protein_match` | Not emitted by AI1; 0. |
| 7 | `cooking_match` | Not emitted by AI1; 0. |
| 8 | `cuisine_match` | Previously 0. Bridge: 1 for an exact requested cuisine / `dish_supported_cuisine` label match after trimming and case folding; otherwise 0. |
| 9 | `meal_category_score` | Not emitted by AI1; 0. |
| 10 | `calorie_fit` | Not emitted by AI1; 0. |
| 11 | `calorie_ratio` | Not emitted by AI1; 0. |
| 12 | `food_match` | AI1 lexical dish-name evidence; 0 if absent. |
| 13 | `semantic_similarity` | AI1 weighted cosine evidence; 0 without a semantic query or if absent. |
| 14 | `dish_similarity` | AI1 dish cosine evidence when a semantic query is encoded; otherwise 0. |
| 15 | `restaurant_similarity` | AI1 restaurant cosine evidence when a semantic query is encoded; otherwise 0. |

AI3 already derives the numeric ratios from hard constraints, with soft-preference
fallback. The patch fixes a missing-data bug: absent price or a zero budget used
to yield `budget_fit=1.0` because an unavailable ratio was represented as zero.
A known zero price with a positive budget still legitimately yields 1.0.

Dish cuisine metadata permits literal comparison without changing retrieval.
Unknown/other/empty labels are not positive evidence. No aliases, translation,
substring matching or restaurant-to-dish cuisine inference is added; for example,
`Việt Nam` and `vietnamese` do not match. Explicit numeric `cuisine_match` values,
including zero, retain priority. `is_vegetarian` does not imply a protein or
category score. Category, protein, cooking, meal and calorie metadata do not
currently reach Candidate even when described in the processed-data schema.
State alone cannot supply those candidate attributes, so they remain zero.

## Real end-to-end prerequisites and runtime limits

This checkout has only `.gitkeep` in `data/processed` and `data/embeddings`.
Real retrieval still needs `restaurants.parquet`, `dishes.parquet`, and
`menu_items.parquet`, plus the restaurant/dish vectors, ID mappings,
`menu_to_vectors.parquet` and `metadata.json` described in
[AI1 retrieval](ai1_retrieval.md). Releases must preserve IDs and pass the existing
hash, dataset-version and mapping checks. Adding a CPU query setting does not
require rebuilding embeddings. Query model weights must also be available locally
for offline inference; the existing lazy constructor can otherwise download them.

Without those files, default retrieval raises a file error. Separately, AI1
requires a location when `max_distance_km` is supplied and explicitly rejects
unsupported hard constraints. It currently supports `budget_max`,
`max_distance_km`, and `vegetarian`; adding artifacts alone does not add support
for every constraint AI2 can express. These existing behaviors are unchanged.
AI3 lazily uses its configured/default CatBoost artifact or the existing weighted
baseline if the artifact is absent; model feature names/order are checked on load.

`recommend()` already supports injected retrieval/ranking functions and needs no
orchestration change. Its stale scaffold docstring has been corrected. The new
`tests/test_ai1_ai3_integration.py` covers the real AI1 conversion path, AI3 adapter,
numeric derivation, missing evidence, precedence, ID preservation, pipeline limits
and device selection without requiring any production data or model downloads.

## Keep AI1 query encoding on CPU alongside AI2 Qwen

Set the environment variable before the first semantic retrieval call:

```powershell
$env:AI1_EMBEDDING_DEVICE = "cpu"
```

Or set `AI1_EMBEDDING_DEVICE=cpu` in the launch environment / an `.env` file that
the application explicitly loads. Retrieval does not load `.env` itself. Unset
or blank preserves SentenceTransformer's automatic device choice. Only the lazy
query encoder reads this option; `embedder.build_embeddings` and injected models
are unaffected. The encoder is reused, so restart the process to change devices
after it has loaded. AI2 settings, including `LOCAL_SLM_ENABLED`, are unchanged.

## Owner follow-up

AI1 owns artifact delivery/validation, optional metadata propagation, and any
future supported-constraint expansion. AI3 should review the literal cuisine
fallback against the external training feature semantics; training notebooks and
feature provenance are not present under `notebooks/ai3` here. Optimization,
broader cuisine normalization, missing-feature policies and model-quality
evaluation remain owner work, not part of this compatibility patch.

## Validation in this checkout

- Baseline retrieval-interface/ranking/pipeline tests before editing: 19 passed.
- Focused integration, retrieval, ranking and pipeline tests after editing:
  62 passed, including all 25 new cases.
- `.venv/Scripts/python.exe -m pytest -q`: 962 passed, 1 failed. The existing
  `tests/test_ai2_ai1_smoke.py::test_ai2_state_can_flow_into_ai1` fails because
  `data/processed/restaurants.parquet` is absent; its loader is not mocked.
- `.venv/Scripts/python.exe examples/integration_demo.py`: passed offline.

No production datasets, embeddings, weights, labels or historical logs were added
or modified to make these checks pass.
