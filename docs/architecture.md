# Tastly architecture

The Next.js frontend proxies `/api/*` to FastAPI. Production backend wiring uses PostgreSQL for catalog presentation, accounts and conversation sessions. It passes a request to AI2, retrieves candidates with AI1, ranks with AI3 and groups the results into primary restaurant recommendations and supplementary suggestions. Map markers preserve restaurant identity.

AI2's LLM-first mode uses an OpenRouter primary/backup chain for structured intent, preference deltas and replies, with safety/grounding and state management. Rules and local Qwen are optional fallback paths. `LOCAL_SLM_ENABLED=false` remains the default. Relative events stay turn-scoped; no numeric relative adjustment policy is invented.

AI1 consumes `UserPreferenceState`, never raw prompts, and returns `list[Candidate]`. It validates external Parquets and embeddings. AI3 consumes state plus candidates and returns `list[RankedResult]`; its default artifact is the included 15-feature CatBoost YetiRank model. Neither module parses prompts. Shared Pydantic schemas live only in `src/common/schemas.py`.

The direct `pipeline.recommend` API accepts injectable dependencies and does not require PostgreSQL/HTTP. `examples/integration_demo.py` uses that boundary with synthetic retrieval/ranking and disabled providers. It is contract verification, not a quality evaluation.

Canonical installed imports are `common`, `conversation`, `retrieval`, `ranking` and `pipeline`; checkout `src.*` aliases remain compatible. Imports do not load models/data or call providers. Query encoder loading and CatBoost loading are lazy at runtime; production startup normally requests a warmup. See [setup](setup.md), [contracts](integration_contract.md) and [restaurant selection](RESTAURANT_RECOMMENDATION_FINAL.md).
