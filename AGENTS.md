# Repository guidance for coding agents

Use Python 3.11+ and Pydantic v2. Inspect the current implementation before
editing. Preserve working AI 2 behavior and backward-compatible public imports.

## Ownership and boundaries

- AI 1: `src/retrieval/`, `data/raw/`, `data/processed/`, `data/embeddings/`,
  `notebooks/ai1/`, `docs/ai1_retrieval.md`, retrieval tests.
- AI 2: `src/conversation/`, `data/ai2_interactive/`, `notebooks/ai2/`,
  `docs/ai2_conversation.md`, existing AI 2 tests.
- AI 3: `src/ranking/`, `models/ranker/`, `models/metadata/`, `notebooks/ai3/`,
  `docs/ai3_ranking.md`, ranking tests.
- Shared, requiring coordinated review: `src/common/`, `src/pipeline/`,
  `src/__init__.py`, dependencies, README, environment examples, CI, contract tests.
  `src/personalization/` is reserved; agree ownership before implementing it.

AI 1 consumes state, never parses natural-language prompts, and returns
`list[Candidate]`. AI 2 parses and manages state; it never retrieves/ranks
restaurants. AI 3 consumes state plus candidates, never parses prompts or retrieves
data, and returns `list[RankedResult]`. Preserve all restaurant/menu/dish IDs.

## Contracts and implementation

Shared schemas live only in `src/common/schemas.py`. Current AI 2 v0.2 definitions
are authoritative. Do not copy older planning schemas or introduce duplicate
Pydantic definitions. Canonical installed imports are `common`, `conversation`,
`retrieval`, `ranking`, and `pipeline`; documented public `src.*` checkout imports
are compatibility aliases. Use canonical names for internal imports.

No module may silently change shared schemas. Update schemas, docs and contract
tests together, notify affected owners in the PR, and pass integration tests.
Keep `context_updates`, canonical removals and turn-level relative event semantics.
Do not persist relative updates or invent numeric adjustment policies.

Unimplemented production modules raise clear `NotImplementedError` at their public
entry points. Synthetic results belong only in tests/examples. Never fabricate
model/data quality, ranking metrics, trained weights, or retrieval completeness.
Imports must not load datasets/models, call providers, or start training.

## Validation and data safety

Run the full `python -m pytest -q` after shared changes, followed by
`python examples/integration_demo.py`. Do not call Gemini/OpenAI in tests;
use mocks and retain offline socket guards. Normal CI must need no API keys.

External API secrets come only from environment variables; never commit `.env`.
`LOCAL_SLM_ENABLED` remains false unless explicitly requested. Do not silently
modify benchmark/test datasets, historical interactive logs, review labels or
exports. Large datasets, embeddings and model checkpoints stay external/ignored
unless explicitly approved. Do not train/download models or datasets as an import
side effect. Check [CONTRIBUTING.md](CONTRIBUTING.md) and module docs before changes.
