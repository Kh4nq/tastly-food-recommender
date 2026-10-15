# Public release verification — 2026-10-15

The public distribution was prepared as a separate export with a new Git history. Latest local source/test changes and intentional file deletions were retained. Functional modules, public imports, shared schemas, dataset IDs and model weights were not rewritten. Notebook execution outputs were cleared; source cells were retained.

## Dataset

The existing [DATA_DOWNLOAD.txt](../data/DATA_DOWNLOAD.txt) and its Google Drive link were preserved. An unauthenticated preview check returned HTTP 200, identified `ai1-demo-data.zip` and did not redirect to sign-in. This checks preview access, not every visitor's download/quota conditions.

The local `ai1-demo-data.zip` was provisioned by the existing validator in an export without active data, using automatic filename discovery. A second isolated destination validated explicit custom-ZIP support. Neither check took the already-installed-data shortcut. Manifest coverage, metadata, checksums, vector shapes, IDs and mappings were validated without regenerating data or weakening checks.

| Property | Validated value |
| --- | --- |
| ZIP SHA256 | `906a818ca4f77782578d0d34226b6741445dfa205f3c463e5ce0b44876c219ed` |
| Usage | `synthetic_demo` |
| Restaurants | 26,025 |
| Dishes | 4,068 |
| Menu items | 173,546 |

These are consistency counts, not verified real-world coverage or quality metrics. The ZIP, extracted datasets, embeddings and manifest payload remain outside Git.

## Validation results

| Check | Result |
| --- | --- |
| Fresh Windows Python 3.11 environment with `setup.ps1 -SkipSlm -SkipFrontend` | Passed; dependency installation, `pip check`, AI1 and AI3 readiness |
| `setup.ps1 -SkipSlm -SkipFrontend -VerifyOnly` | Passed; optional Qwen/Gemini capabilities unavailable/unconfigured as expected |
| Guarded full Python suite, existing environment | 1,852 passed, 49 skipped |
| Guarded full Python suite, freshly installed export environment | 1,852 passed, 49 skipped |
| Protected-benchmark reader tests after excluding the prompt file from export | 92 passed, 26 skipped |
| `examples/integration_demo.py` | Passed, offline injected example |
| Frontend `npm ci` | Passed using the committed lockfile |
| Frontend `node --test tests/*.test.mjs` | 19 passed |
| Frontend ESLint and TypeScript `--noEmit` | Passed |
| Next.js production build | Passed, including route generation |
| Isolated PostgreSQL 17 schema/indexes/procedures and empty-database seed | Passed |
| Production backend startup/readiness with real cached query encoder and CatBoost warmup | Passed |
| HTTP form search and restaurant presentation | Passed; three results with preserved IDs and no retired explanations |
| Built frontend HTTP and `/api` proxy search | Passed |
| Public README/setup/artifact local links | Passed |
| Public-file and ignore-rule audit | No detected credential values/tokens/private keys, developer paths, dataset payloads or unresolved LFS pointers |

The initial plain `python -m pytest -q` run encountered the existing freeze-audit hook's protection of benchmark paths: 9 failures and 6 setup errors, alongside 1,855 passes and 31 skips. The supported guarded command is documented in README/CONTRIBUTING; it preserves benchmark restrictions and passes. The protected prompt file is intentionally external to the public distribution. No test expectations, benchmark labels or access guards were weakened to obtain a passing result.

Some checks initially hit sandbox restrictions on network/child processes and were rerun with permitted access. Google Fonts access was required for the build. No paid provider calls, training, dataset regeneration or new model downloads were performed. Runtime smoke tests loaded the already-cached query encoder. Their temporary database/container and local server processes were stopped afterward; no existing database or user data was used.

## Distribution decisions and remaining setup

Excluded: credentials and `.env`, interaction/labeling records and traces, protected benchmark prompts, dataset archives and extracted data, embeddings, local IDE/agent launch settings, presentation materials, backups, logs, caches, dependency folders, generated builds and optional Qwen weights/tokenizer bundles. Authored setup scripts, optional Kaggle runners, essential tests, frontend assets, contributor credits, CatBoost models and Qwen configuration/chat template remain included. There are no Git LFS filters or pointer-only artifacts.

The README and setup/artifact/architecture guides describe the public distribution. `.env.example` selects the OpenRouter LLM-first chain with an empty API-key field, keeps local Qwen disabled and allows the documented request timeout. Setup/provisioning behavior and checksum validation are preserved; optional-adapter diagnostics point to the external bundle instructions.

Visitors must download the demo ZIP, configure their own OpenRouter key and local PostgreSQL credentials, install requirements and start the backend/frontend. First live query encoding needs the Hugging Face model unless already cached. Mapbox/Web3Forms and local Qwen are optional and need separate configuration/artifacts. Provider inference and Qwen inference were not tested. Asset licensing provenance and independent model evaluation remain documented limitations; no blanket license or quality claim was invented.
