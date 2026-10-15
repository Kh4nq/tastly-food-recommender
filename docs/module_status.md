# Module status

| Module | Owner | Status | Public Entry Point | Tests | Notes |
| --- | --- | --- | --- | --- | --- |
| AI 1 Retrieval | AI1 | Implemented | `retrieval.retrieve_candidates` | Retrieval and integration tests | Validated v3-menu Parquets/embeddings required |
| AI 2 Conversation | AI2 | Implemented, Preference v0.2 | `conversation.parse_user_input`, `update_state`, `process_user_request` | Offline parsing/routing/state tests | OpenRouter LLM-first chain; optional external Qwen adapter |
| AI 2 Labeling | AI2 | Implemented local review pipeline | `scripts/prepare_ai2_slm_data.py`, `review_ai2_labels.py`, `export_ai2_training_set.py` | Offline labeling and optional UI tests | Held-out benchmark exclusion; candidate labels require human review; no training/inference |
| AI 3 Ranking | AI3 | Implemented CatBoost YetiRank | `ranking.rank_candidates` | Ranking and integration tests | Tracked 15-feature model; existing weighted fallback if absent |
| Common contracts | Shared | Implemented | `common.schemas`, `common.interfaces` | `test_common_contracts.py`, `test_module_imports.py` | Interface version 0.2; existing AI 2 definitions unchanged |
| Pipeline | Shared | Injectable orchestration implemented | `pipeline.recommend` | `test_pipeline_mock.py`, AI1/AI3 integration | Defaults use real modules; external artifacts required |
| Frontend | Frontend | Integrated demo frontend | Existing package scripts | npm lint/build | Structure and backend integration not frozen |
| PostgreSQL | Backend | Required by production website wiring | `database` package | Repository tests; Compose healthcheck | Not required by the direct AI pipeline |
| Personalization | Unassigned/shared | Reserved | None | Import smoke coverage | No learned preference model or profile storage |

Historical test counts are recorded in the development reports; see the public release verification for current checks. Integration
tests are structural validation, not retrieval/ranking quality evidence. Historical
reports retain their original observations. See [setup](setup.md) for regression
commands that protect the sealed benchmark and [artifact audit](artifact_audit.md)
for current availability.
