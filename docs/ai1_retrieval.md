# AI1 Retrieval

## Purpose

AI1 receives a normalized `UserPreferenceState` from AI2 and returns a list of `Candidate` objects for AI3.

AI1 does not parse natural-language prompts and does not perform the final ranking.

```text
UserPreferenceState
        |
        v
Hard filter
        |
        v
Geo filter / distance
        |
        v
Lexical food-name evidence
        |
        v
Semantic/vector retrieval
        |
        v
Candidate[]
```

## Production entry point

```python
from retrieval import retrieve_candidates
```

```python
retrieve_candidates(
    state: UserPreferenceState,
    top_k: int = 100,
) -> list[Candidate]
```

## Required processed data

AI1 currently expects:

- `data/processed/restaurants.parquet`
- `data/processed/dishes.parquet`
- `data/processed/menu_items.parquet`

The current dishes dataset contains metadata including:

- `dish_name`
- `description`
- `ingredients`
- `cooking_method`
- `calories`
- `primary_category`
- `meal_role`
- `main_protein`
- `primary_cooking_style`
- `is_vegetarian`
- `cuisine_origin`
- `supported_cuisine`

## Retrieval stages

### Hard filtering

Hard constraints such as minimum/maximum budget and maximum distance are applied before semantic retrieval and before AI3 ranking.

AI1 supports `budget_min`, `budget_max`, `max_distance_km`, and `vegetarian`.
With the evidence-backed profile release below, it additionally supports
`parking`, `wifi`, `air_conditioning`, `outdoor_seating`, and `wheelchair_accessible`.
Both true and false express a required value; unknown values never satisfy it.
Budget bounds are inclusive and expressed in VND: for example,
`hard_constraints={"budget_min": 35000, "budget_max": 50000}` keeps menu prices
from 35,000 through 50,000 VND. Either bound can be supplied independently;
an inverted range raises `ValueError`. Filtering uses `price_vnd`, or
`estimated_price_vnd` when `price_vnd` is absent. This code change requires no
processed-data or embedding rebuild.

### Lexical food matching

AI1 derives `food_match` directly from `dish_name`.

Scoring:

- `1.0`: exact food-name match
- `0.95`: dish name starts with the requested food
- `0.9`: requested food appears as a whole word/phrase elsewhere
- `0.85`: supported qualified/reordered name containing all requested tokens
- `0.0`: no lexical match

Active food matching folds Vietnamese accents/case and uses whole tokens, with
explicit protection against phô mai/pho mát (cheese), dessert/beverage heads and
different dish families. Names of restaurants are never menu evidence.

Examples:

```text
phở -> Phở Bò        match
phở -> Phở cuốn      match
phở -> Phô Mai       no match
phở tái -> Phở bò tái  qualified direct match
phở tái -> Phở bò      alternative only
```

### Semantic retrieval

Positive preference fields are converted into Vietnamese UTF-8 query text.

Examples:

```text
Món ăn: phở
Ẩm thực: Việt Nam
```

Numeric hard constraints such as budget and distance are not embedded into the semantic query.

Semantic scoring is used to select candidates for AI3. AI1 does not perform the final recommendation ranking.

Named-dish retrieval now retains bounded primary and supplementary pools. Primary
has `food_match>0`. Supplementary requires the same recognized dish family in
the dish name plus dish-only cosine >=0.25; this conservative floor is a heuristic,
not a quality metric. Unknown families receive no guessed alternatives.
Every pool passes the same hard filters. Broad zero-match rows are not fillers.
`recommendation_group` and `alternative_evidence` travel in `match_features`.

Preselection takes menu items in rounds across restaurant IDs and reserves room
for both pools. It retains multiple menus when capacity permits, never reintroduces
a known matching venue as a supplementary-only venue, and respects the existing
candidate limit. Web searches request max(configured retrieval limit, 4*K),
capped at 1,000 rows; actual AI3 scoring precedes restaurant grouping/Top-K.

The existing restaurant vectors embed display names. Their similarity is now
neutralized to 0 and semantic_similarity uses dish similarity so synthetic brand
names cannot affect selection or CatBoost inputs. Vectors and model stay intact.
See [final recommendation handoff](RESTAURANT_RECOMMENDATION_FINAL.md).

## AI1 -> AI3 Candidate contract

AI1 preserves:

- `restaurant_id`
- `menu_item_id`
- `dish_id`

Top-level retrieval evidence includes, when available:

- `distance_km`
- `price`

`Candidate.match_features` includes:

- `food_match`
- `semantic_similarity`

Additional evidence may include:

- `dish_similarity`
- `restaurant_similarity`
- `dish_supported_cuisine`
- `is_vegetarian`

AI1 does not fabricate downstream ranking features that cannot be derived from retrieval evidence.

## Restaurant profile release (12 October 2026)

The active data has subsequently switched, at the user's request, to an explicitly
labeled [coherent synthetic demo](DEMO_DATASET.md). The source-backed release below
remains available as a backup. Synthetic profile acceptance requires a demo
manifest and row-level demo labels; it is not enabled for ordinary source releases.

Data is prepared in the sibling `mlai-food` project, not inside the application:

```powershell
cd ..\mlai-food
python scripts/30-build-ai1-profiles.py
python scripts/30-build-ai1-profiles.py --publish
```

The first command snapshots the exact currently deployed Parquets, validates
their hashes against the embedding metadata, fixes the OSM join through original
source IDs and builds `data/releases/ai1-profile-v1/processed`. The second copies
only the new sidecar, manifest and QA report into recommender `data/processed`:

- `restaurant_profiles.parquet`
- `ai1_profile_manifest.json`
- `ai1_profile_quality_report.json`

The three baseline Parquets and all vectors/menu mappings stay byte-identical.
The loader verifies the sidecar hash, baseline hashes, exact restaurant ID
coverage, nullable boolean types and field evidence. Legacy releases without
sidecars remain usable; they cannot satisfy the new amenity hard constraints.
An incomplete or mismatched sidecar fails validation. Restart running backend
processes after changing files because the Retriever is cached.

OSM `internet_access=wlan` establishes source-reported Wi-Fi;
`internet_access=yes` only establishes internet, so Wi-Fi stays unknown.
`wheelchair=limited` stays unknown for full wheelchair accessibility. Outdoor
seating types such as patio/garden are normalized by a field-specific rule.
Known values carry source, original source ID, raw tag and method. They are
source-reported observations, not current field verification.

The current release has 2,905 Wi-Fi true, 464 AC true, 1,033 outdoor-seating true
and 227 wheelchair-accessible true restaurants. One reviewed Hum Garden branch
has car parking evidence; vehicle-specific requests require matching evidence scope.
Quiet and family-friendly attributes have no evidence in this source and remain null.
Ratings, route travel time and restaurant allergen safety are also unsupported.
Unsupported hard constraints and wholly unknown required amenities become
controlled HTTP 422 errors (`unsupported_constraint` / `unverifiable_constraint`)
with a suggestion to relax the requirement, not an HTTP 500 or silent fallback.

Candidate dish metadata now includes category, meal role, protein, cooking style,
calories, ingredients, cooking method and provenance. Restaurant profile values
and their evidence appear in `restaurant_features`. No public schema, ID or
numeric similarity meaning changes. AI3 now derives category/protein/cooking,
meal-category and calorie features from this metadata, matching the V3 meal/calorie
definitions. Explicit numeric feature values retain compatibility priority.
The 15-feature CatBoost layout and model weights are unchanged.

Categorical occasion, companions and meal time can enter the positive query;
identity, party size, transport and negatives do not. Exact normalized negative
labels such as noisy/spicy are matched separately against explicit attributes.
Absent spice metadata does not certify that food is non-spicy. Supported soft
amenities and family context use matching evidence before top-k selection:
food match first, fewer evidence mismatches, more evidence matches, then the
existing semantic/geo ordering. Counts are selection tie-breaks, not model scores.
Candidate `match_features.preference_evidence` records matched, mismatched,
unknown and unresolved labels. Unknown contributes no match or violation.

See [the Vietnamese implementation guide](AI1_FIX_12-10-26.md) and
`mlai-food/reports/qa/ai1-profile-v1` for actual data reports. No review text was
generated. Source listings were reviewed for the explicitly matched Hum branch.
Menus/prices remain synthetic. The fixed Git-baseline benchmark reports
source/catalog known-label Recall@K, not human relevance or subjective quality.
Experimental generated profiles remain separate and are rejected by production.
HTTP warnings expose unknown/mismatched/unresolved soft preferences.

For Kaggle, ship these three profile files alongside the existing processed data
and paired embeddings in the data Dataset. Ship the updated Python/UI code in
the code Dataset. The code packager intentionally excludes `data/`; uploading
only the code ZIP will not deliver the new profiles.

See the [AI1 -> AI3 integration audit](ai1_ai3_integration.md) for exact feature
coverage and artifact prerequisites. Set `AI1_EMBEDDING_DEVICE=cpu` before the
first semantic retrieval call to keep the query encoder off AI2's GPU. Unset or
blank retains automatic device selection; offline embedding generation is unchanged.

## Embedding artifacts

AI1 uses embedding artifacts stored under:

```text
data/embeddings/
```

Dataset version:

```text
v3-menu
```

Embedding model:

```text
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

Embedding configuration:

- normalized: `true`
- dtype: `float32`
- batch size: `64`
- vector dimension: `384`

Current artifact counts:

- restaurants: `26,025`
- dishes: `4,000`
- menu mapping: `336,167`

Artifact files:

```text
restaurants_vectors.npy
restaurants_ids.csv
dishes_vectors.npy
dishes_ids.csv
menu_to_vectors.parquet
metadata.json
```

The metadata records SHA256 hashes for the vector artifacts and processed source parquet files.

Source parquet files tracked by the current metadata:

```text
restaurants.parquet
dishes.parquet
menu_items.parquet
```

## Artifact integrity and rebuild rule

Before demo or deployment, verify that the processed parquet files match the SHA256 values recorded in `data/embeddings/metadata.json`.

Embedding artifacts must be regenerated whenever embedding inputs change:

- `restaurants.parquet`
- `dishes.parquet`
- `menu_items.parquet`
- embedding model
- text construction logic used by the embedder
- normalization applied before embedding

Source-file hashes verify parquet contents, but they do not by themselves prove that the embedding text-template code is unchanged.

For filter/display-only enrichment, vectors may be reused only after proving
exact per-ID text equality and updating all release manifests. See
[serving and space taxonomy](serving_taxonomy.md) for the versioned updater.

## Known data-quality limitation

Some current menu rows use IDs such as:

```text
synthetic_menu_v2:*
```

Therefore a dish-to-restaurant association may be technically valid in the current dataset while not necessarily representing a verified real-world restaurant menu.

This is a dataset-quality limitation rather than an AI1 retrieval-logic issue.

## Verification

Run AI1-specific tests:

```powershell
pytest tests/test_retrieval_retriever.py -q
pytest tests/test_ai2_ai1_smoke.py -q
```

Run the full repository regression suite:

```powershell
python -m pytest -q -p scripts.sealed_benchmark_guard
```
