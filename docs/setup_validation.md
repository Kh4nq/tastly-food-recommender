> Historical development report. Use the [public README](../README.md) and [setup guide](setup.md) for the current distribution.

# Setup preparation validation — 2026-10-07

## Final setup robustness pass

The following results supersede the setup/provider details in the earlier
preparation record below; the earlier results remain historical evidence.

- `setup.ps1` and the default CI install now use `.[test,ai1,ai3,gemini,db]`.
  OpenAI is optional/legacy and requires manual `.[openai]` installation. Its
  implementation and tests are unchanged; normal setup needs neither OpenAI
  environment variable nor SDK.
- NVIDIA detection precedes SLM installation. No detected GPU means no `slm`
  extra installation. CUDA availability and a tensor operation, dependency
  imports and adapter checks gate Local SLM readiness. Missing CUDA or a failed
  optional SLM install leaves working core dependencies usable with Gemini.
  No CUDA wheel source or driver installation was added.
- Setup prints separate core, AI1, AI3, SLM, Gemini, frontend and PostgreSQL
  statuses, including on failure. Preflight reports statuses through a temporary
  JSON file containing no secrets. Gemini configuration is checked without API
  calls or persistent environment changes.
- README, setup instructions and `.env.example` recommend Gemini. Existing `.env`
  files remain untouched and Local SLM stays opt-in. The preservation message
  already reads `nothing was overwritten`; the reported typo is absent.
- Frontend still uses `npm ci`, remains optional, and retains explicit
  `-WithFrontend` failure behavior. Database startup and `--if-empty` seeding are
  unchanged. The sealed-benchmark guard is unchanged.

Validation used `.venv311/Scripts/python.exe`:

| Check | Result |
| --- | --- |
| Setup/preflight tests with sealed guard | **28 passed** |
| Full `python -m pytest -q -p scripts.sealed_benchmark_guard` | **961 passed, 26 skipped** |
| `python -m pip check` | No broken requirements |
| `python examples/integration_demo.py` | Passed, offline |
| `./setup.ps1 -VenvPath .venv311 -VerifyOnly -SkipFrontend` | Passed; core, AI1, AI3 and SLM prerequisites READY; Gemini CONFIGURED; frontend/database SKIPPED |

Nineteen additional tests cover configuration presence, unavailable/broken CUDA,
missing SLM dependencies, and mocked PowerShell setup paths. The PowerShell tests
run each scenario twice, including no GPU, failed/empty NVIDIA queries, optional
SLM installation failure, core/artifact failures, frontend failures, database
seeding and verify-only mode. All external commands in that harness are mocked.
Fresh dependency installation, live npm installation and live Docker startup were
not rerun during this pass. The actual environment was verified without package
reinstallation. No AI implementation, shared schema, model weight, dataset,
frontend source or benchmark semantics changed. No provider API was called and
the sealed benchmark was neither read nor run.

## Earlier preparation record

Repository hygiene, active documentation, artifact auditing and setup only.
No files under the AI1/AI2/AI3 implementations, shared schemas or pipeline were
modified. No weights, training logic, datasets, source IDs or recommendation
behavior changed. No provider call, model download, training or Qwen inference
was performed. The sealed AI2 benchmark was not read or executed.

## Changes

Added:

- `setup.ps1`: Python 3.11 environment, existing dependency extras, LFS handling,
  preserved `.env`, optional frontend/database, preflight and verify-only mode.
- `scripts/preflight.py`: read-only artifact/dependency/CUDA checks.
- `scripts/sealed_benchmark_guard.py`: opt-in regression skips plus an audit hook
  that blocks attempts to open the sealed benchmark before reading its contents.
- `tests/test_setup_preflight.py`: nine synthetic artifact/seed safety cases.
- `docs/setup.md`, `docs/artifact_audit.md`, and this validation record.

Updated:

- `.gitignore`, `.env.example`, `CONTRIBUTING.md`, `README.md`.
- `.github/workflows/ci.yml`: fixed a name-only invalid step, installed required
  offline extras, enabled the sealed-data guard, explicitly excluded the real-data
  smoke test because CI has no external V3 package.
- `scripts/seed_database.py`: V3 menu count and an additive `--if-empty` option
  that locks/checks tables before seeding; existing default replace-all operation
  remains available for explicit manual use.
- `database/README.md`; active `docs/architecture.md`, `module_status.md`,
  `ai1_retrieval.md`, `ai2_conversation.md`, `ai3_ranking.md`, `data_schema.md`,
  `integration_contract.md`, and `team_ownership.md`.
- Historical `docs/integration_scaffold_report.md` and
  `docs/ai1_ai3_integration.md`: added historical notices; original evidence retained.

Active documentation now describes implemented retrieval/CatBoost ranking,
Qwen3-1.7B + LoRA V3 routing, v3-menu and 336,167 menu rows, real Git metadata,
manual artifacts, optional PostgreSQL and a developing frontend. Unrelated
historical milestone reports and AI2 operational/review tooling were preserved.

## Cleanup

Removed 16 generated Python/pytest cache directories, `repo_tree.txt`,
`repo_files.txt`, and the 12-file `tmp_dataset_v3` duplicate tree. Every temporary
V3 file matched its active counterpart by SHA256, and the active package passed
the existing Retriever validation before deletion.

Preserved `.venv311`, `.venv`, active editable-install egg-info, both existing logs,
all model artifacts, datasets/exports, notebooks, fixtures, original tests/scripts,
and benchmark files. No frontend source/package/lockfile changes were made.
Installed frontend dependencies/build output remain local and ignored.

## Commands and results

Python commands below used `.venv311/Scripts/python.exe` to preserve the validated
environment. Setup's conventional default is `.venv`, not `.venv311`.

| Command / check | Result |
| --- | --- |
| `python -m pytest -q -p scripts.sealed_benchmark_guard` | **942 passed, 26 skipped** |
| `python examples/integration_demo.py` | Passed, offline injected integration |
| `python -m pip check` | No broken requirements |
| `./setup.ps1 -VenvPath .venv311 -VerifyOnly` (repeated) | Passed; CUDA, V3 artifacts, adapter, project imports; OpenAI SDK warning |
| `python scripts/preflight.py` | Required checks passed after optional OpenAI handling; no models loaded |
| Simulated CPU preflight | Exit 0 with external fallback; `--require-local-slm` exits 1 as intended |
| PowerShell parser and existing-venv ownership probe | Passed |
| CI YAML parse / executable step check | Passed; GitHub-hosted CI not run here |
| `npm ci --no-audit --no-fund` in `src/frontend` | Passed with registry access, 371 packages installed |
| `npm run lint` | **Failed: 2 errors, 7 warnings**, existing frontend code |
| `npm run build` | Passed with network access for existing Google Fonts imports |
| `git diff --check` | Passed |
| `git ls-files`, `git check-ignore`, `git lfs ls-files`, targeted `git show`/history and SHA256 comparisons | Artifact classifications and duplicate verification recorded in artifact audit |

The supplied baseline was 951 passed / 8 skipped. This run preserves the eight
existing skips, adds 18 skips for sealed-benchmark readers, and adds nine passing
setup tests: 933 existing + 9 new passes, 8 existing + 18 protected skips.
It is not a claim that the excluded tests were rerun. Initial validation exposed
four additional indirect benchmark readers; the audit hook blocked all reads.
Those tests were subsequently added to the explicit skip list. The final run has
no failures and preserves existing offline socket guards and benchmark semantics.

Frontend lint errors are `react-hooks/immutability` at
`src/frontend/components/layout/LangToggle.tsx:18` and
`src/frontend/components/layout/LocationPicker.tsx:19`. They were reported without
refactoring UI behavior. Initial npm/build attempts were sandbox-network limited;
approved retries completed installation/build. The frontend lockfile is unchanged.

## Readiness and limits

All audited production artifacts are present locally. AI2 adapter weights/tokenizer
JSON are Git LFS-managed and match their pointer hashes. Both CatBoost files use
ordinary Git. The older file is an unreferenced historical 11-feature model,
incompatible with the current 15-feature schema; retained pending AI3 review.
AI1 artifacts are ignored/local only. Qwen and the AI1 query encoder are externally
cached; cache completeness/inference was not tested. See [artifact audit](artifact_audit.md).

On NVIDIA machines, setup checks the driver, Torch CUDA operation, SLM imports and
adapter, recommends `AI1_EMBEDDING_DEVICE=cpu`, and leaves Local SLM opt-in. Actual
checks passed on a GTX 1650 with Torch 2.14.1+cu130. CPU/no-CUDA machines retain
Gemini fallback; no-GPU warnings are nonfatal by default. Legacy OpenAI is optional
and requires manual `python -m pip install -e '.[openai]'` installation.

Frontend setup is optional/loosely coupled; `-WithFrontend` makes it required.
PostgreSQL uses the existing Compose healthcheck/schema/indexes/functions only with
`-WithDatabase`, and seeds an empty database only when processed files exist.
Docker was unavailable in this environment, so live Compose startup/SQL/seed were
**not exercised**. The non-overwrite seed behavior has a mocked offline test.
Full fresh-clone dependency provisioning was not run against the working Python
environment; syntax, ownership, repeated verification and synthetic failure paths
were checked without reinstalling its packages.

Remaining prerequisites/follow-up: publish the canonical AI1 V3 artifact package
and checksums;
exercise Docker setup on a Docker-equipped machine; have frontend owners fix lint;
review platform/CUDA dependency locks and historical CatBoost provenance. Existing
dependency ranges are not an exact reproducibility lock.
