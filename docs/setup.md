# Public distribution setup

The current supported instructions are in the [root README](../README.md#windows-powershell-setup). Run commands from the clone root with Python 3.11.

```powershell
.\setup.ps1 -SkipSlm -WithDatabase -WithFrontend
.\.venv\Scripts\python.exe -m uvicorn backend.main:create_production_app --factory --port 8000
```

Start Next.js in another terminal under `src/frontend` with `npm.cmd run dev`.
PostgreSQL is required by production backend wiring; a database server and Node.js are not required for the direct AI-only pipeline or fixture-based Python tests.

Download `ai1-demo-data.zip` using [DATA_DOWNLOAD.txt](../data/DATA_DOWNLOAD.txt), place it at `data/ai1-demo-data.zip`, or pass `-AI1ArtifactZip` to setup. ZIP roots contain `processed/`, `embeddings/` and `dataset_manifest.json`. Setup stages and validates missing/invalid active artifacts using the existing checksums, metadata, IDs and mappings. Valid active data is preserved and causes the ZIP to be ignored, even with an explicit ZIP argument. Setup never regenerates data.

Use `.env.example` for OpenRouter configuration; keep credentials in backend `.env`/process variables. `LOCAL_SLM_ENABLED=false` remains the default. `-SkipSlm` avoids optional CUDA dependencies and `-SkipFrontend` skips Node/npm setup. Omit `-WithDatabase` for AI-only setup. Existing `.env`, unrelated environments and nonempty databases are preserved. Use `-VenvPath .venv-tastly` for a separate environment.

```powershell
.\setup.ps1 -SkipSlm -SkipFrontend
.\.venv\Scripts\python.exe -m pytest -q -p scripts.sealed_benchmark_guard
.\.venv\Scripts\python.exe examples/integration_demo.py
.\setup.ps1 -SkipSlm -SkipFrontend -VerifyOnly
```

Before downloading data, add `--ignore=tests/test_ai2_ai1_smoke.py` to the guarded test command. Optional dependencies can cause skips. The unguarded full suite can encounter benchmark access denied by the existing freeze-audit hook; the guarded command preserves that protection. Neither normal CI nor these checks requires paid API calls. The existing offline socket guards remain active.

`-VerifyOnly` checks an existing environment/artifacts and never provisions a ZIP or starts services. It cannot be combined with `-WithFrontend`/`-WithDatabase`. Preflight checks configuration/cache presence, not provider inference, database connectivity or complete model loading. Gemini and Qwen are optional capability paths.

The public repository has no LFS objects. CatBoost models are ordinary Git files; Qwen weights/tokenizers and the Hugging Face base/query models are external. See [artifact inventory](artifact_audit.md) and [optional adapter notes](../models/ai2/ai2-qwen3-1.7b-lora-targeted-v3/README.md). The frontend's npm lockfile is included; Python uses bounded dependency ranges rather than a complete lockfile.
