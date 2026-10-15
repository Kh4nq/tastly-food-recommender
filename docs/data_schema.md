# Data ownership and artifact schema

AI 1 owns raw/processed/embedding data. AI 2 owns private interactive records and
reviewed exports. AI 3 owns ranking artifacts and evaluation metadata. The active
AI1 package is v3-menu (26,025 restaurants, 4,000 dishes, 336,167 menu rows).
See [artifact audit](artifact_audit.md) for delivery and checksum status.

## Identifier contract

| Identifier | Meaning | Requirement |
| --- | --- | --- |
| restaurant_id | Restaurant identity across retrieval/ranking/backend | Required opaque string; preserve exactly |
| menu_item_id | Specific restaurant menu listing | Optional only for restaurant-only candidates; preserve when present |
| dish_id | Canonical dish identity where available | Optional; preserve when present |

Do not convert, hash, renumber or synthesize IDs between Candidate and RankedResult.
AI 1 must document any upstream source-to-canonical mapping once, with provenance,
before integration; the backend and AI 3 consume the same published IDs. Menu items
must reference their restaurant; dish relationships require source evidence.
Uniqueness/cardinality and cross-source collisions need explicit ingestion policy.

## Processed tables and artifact contracts

| Table/artifact | Key/links | Fields to document |
| --- | --- | --- |
| Restaurants | food_place_id (mapped to Candidate.restaurant_id) | name, coordinates, cuisine, facilities, rating, source/version |
| Menu items | menu_item_id -> food_place_id; dish_id | name, integer VND price, availability, source/version |
| Dishes | dish_id | canonical labels/aliases, source/version |
| Embeddings | exact source entity ID + embedding version | model, input text recipe, dimensions, index version |
| Ranking metadata | model/feature/dataset version | schema, metrics protocol, artifact location/checksum |
| Interactive records | existing AI 2 session/turn metadata | schema_version=0.2, reviewed status and provenance |

The first four rows describe the implemented AI1 artifacts; field summaries are
not exhaustive. Consult `src/retrieval/hard_filter.py`, `src/retrieval/embedder.py`
and `database/schema.sql` for loader requirements and optional database types. Coordinates use decimal degrees; distance uses km; price uses integer VND.
Document unknown values and synthetic/derived field provenance separately.

## Tracking policy

Track small fixtures (prefer `tests/data/`), schema examples, small metadata/config
and tiny demo data. New raw/processed/embedding directories track only `.gitkeep`
by default; any small approved exception needs a narrow reviewed ignore rule.

Usually external/untracked: raw OSM dumps, full ViFoodRec, large generated parquet,
huge embeddings, model checkpoints/SLM weights and private interactive logs.
`models/metadata/` may track small configs. Both current CatBoost binaries are
Git-tracked. The AI2 V3 adapter is tracked with weights/tokenizer JSON in Git LFS;
Qwen base weights and AI1 data remain external. Keep notebook outputs reasonable.

The existing `tests/data/conversation_cases.json`, benchmark prompt source,
`examples/ai2_mvp_traces.json` and audit documents remain untouched. Generated
benchmark results and historical interactive data remain ignored and unmodified.
No source fixture is covered by the new large-artifact directory rules.
