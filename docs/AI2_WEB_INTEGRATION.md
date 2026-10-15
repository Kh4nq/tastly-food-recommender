# Local AI2 fullstack integration — 2026-10-15

The AI2 runtime from `<development-checkout>` is integrated into
`.`. No paid provider call was run.
Real catalog/database/cloud testing through a browser remains pending.

## Integration and boundaries

Browser chat and filters use `buildSearchRequest` → same-origin `/api/search` →
the existing Next rewrite → FastAPI → `SearchService` →
`Ai2ConversationAdapter` → `conversation.process_user_request`.
The backend cookie owns session identity. Accepted AI2 state feeds the existing
retrieval, ranking, map lookup and PostgreSQL session store. A failed downstream
turn still leaves stored state unchanged.

The adapter already calls the correct public service; its interface and wiring
were retained. The backend now skips **both ranked and map retrieval** when AI2
requires clarification, and returns AI2's state with empty results. Chain failure
therefore preserves the prior state without presenting recommendations.

Transferred runtime files retain the source's rules, evidence/safety checks,
scoped allergy retractions, provider profiles, State Manager, rollback,
normalization, Qwen loading and lazy provider cache. The target's existing
serving-style rule/form blocks were retained in parser.py and rule_parser.py.
Shared schemas, public imports, prompts, backend routing, frontend source,
database code, AI1/AI3 algorithms and historical artifacts were preserved.
Unrelated labeling/training/review workflows were not imported.

OpenRouter uses the standard library HTTP client; no new dependency is needed.
The existing `slm` extra already declares Torch, Transformers, PEFT, Accelerate
and bitsandbytes for both adapters. The chain uses exactly
`google/gemini-3.5-flash-lite` followed by `openai/gpt-5.4-mini`.

## Local model preservation

| Selection | Target path | Storage |
| --- | --- | --- |
| v3, default/rollback | models/ai2/ai2-qwen3-1.7b-lora-targeted-v3 | Existing target files preserved |
| v4, experimental opt-in | models/ai2/best_adapter_v4_experimental | Directory junction to the source's existing V4 folder |

No weights, environment, credentials or source logs were copied. V4's junction
avoids duplicating weights and tokenizer assets. Its target must remain available
on this machine; this local junction is not a portable Git artifact. Loading uses
the shared artifacts read-only. An absolute external adapter path also works via
`LOCAL_SLM_ADAPTER_PATH`; an explicit path takes precedence over VERSION.

Both adapters were actually loaded and generated schema-valid output in separate
processes, with sockets blocked and cache-only base loading. Each loaded 196 NF4
linear layers and 392 LoRA parameter tensors on CUDA, with zero meta parameters.
Their weight hashes match the supplied handoff. These single authored probes
establish local load/generation functionality, not general model quality.

Validation reused the source's existing Python 3.11 environment read-only, with
`-B` and target-first `PYTHONPATH`; imports were checked to resolve to this checkout.
No virtual environment was copied or installed into the source repository.

## Before real web testing

Preflight reports nine missing AI1 files under `data/processed` and
`data/embeddings`. Obtain the matching reviewed artifact package; the newer web
serving-style controls require a release containing that taxonomy. Do not silently
substitute the source checkout's older catalog, regenerate data or disable filters.
The current missing-data test failure is
`tests/test_ai2_ai1_smoke.py::test_ai2_state_can_flow_into_ai1`.

PostgreSQL must be reachable, with the existing schema/procedures and catalog
matching the AI1 IDs. No database was changed during integration. This checkout
has no root `.env`; configure the server's DATABASE_URL and key yourself. Full
production readiness has not been established.

AI1 currently rejects unsupported allergy/ETA constraints rather than certifying
results without evidence. These remain end-to-end limitations: a retrieval error
keeps the prior saved state under the existing transaction contract, so a new
allergy in that failed search is not committed. The mocked HTTP tests establish
AI2/session behavior when retrieval succeeds, not real allergen enforcement or
successful allergy-state persistence after a catalog error.

The commands below use the already validated environment without copying it.
For an independent environment, create a new target-local Python 3.11 venv and
install the existing extras; do not copy an environment or repoint the source's
editable installation. Change `$Python` accordingly.

Optional initial local data/DB preparation, **only after supplying the reviewed ZIP**:

```powershell
Set-Location '.'
$Python = '.\.venv\Scripts\python.exe'
$env:PYTHONPATH = "$PWD\src;$PWD"
$env:PYTHONDONTWRITEBYTECODE = '1'
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
# Edit .env for your LOCAL database. Keep API credentials server-side.
& $Python -B scripts/setup_artifacts.py --zip data/ai1-demo-data.zip
if ($LASTEXITCODE -ne 0) { throw 'AI1 artifact validation failed' }
& $Python -B scripts/preflight.py
if ($LASTEXITCODE -ne 0) { throw 'Resolve preflight failures before starting services' }
docker compose up -d postgres
# Wait for postgres to be healthy in `docker compose ps` before applying SQL.
# These names match .env.example; use your configured user/database if different.
foreach ($sqlFile in @('schema.sql', 'indexes.sql', 'procedures.sql')) {
    docker compose cp "database/$sqlFile" "postgres:/tmp/$sqlFile"
    if ($LASTEXITCODE -ne 0) { throw 'SQL copy failed' }
    docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U mlai -d mlai_food -f "/tmp/$sqlFile"
    if ($LASTEXITCODE -ne 0) { throw 'SQL application failed' }
}
# Loads DATABASE_URL using the existing backend loader; preserves nonempty catalogs.
& $Python -B -c 'from backend.settings import load_environment; load_environment(); from scripts.seed_database import main; main(if_empty=True)'
```

## Start backend — PowerShell terminal 1

Run this after the data/database prerequisites are satisfied. Setting these
variables does not itself call a paid API; a model-routed web request will.

```powershell
Set-Location '.'
$Python = '.\.venv\Scripts\python.exe'
$env:PYTHONPATH = "$PWD\src;$PWD"
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:LLM_PROVIDER = 'openrouter_chain'
$env:OPENROUTER_ENABLED = 'true'
$env:OPENROUTER_PRIMARY_MODEL = 'google/gemini-3.5-flash-lite'
$env:OPENROUTER_BACKUP_MODEL = 'openai/gpt-5.4-mini'
$env:OPENROUTER_CHAIN_MAX_TOKENS = '512'
$env:OPENROUTER_TIMEOUT = '30'
$env:BACKEND_AI_TIMEOUT_S = '120'
$env:LOCAL_SLM_ENABLED = 'false'
$env:AI1_EMBEDDING_DEVICE = 'cpu'
$env:CONVERSATION_LOG_ENABLED = 'true'
$env:CONVERSATION_LOG_PATH = "$PWD\logs\web-ai2-smoke.jsonl"
$secureKey = Read-Host 'OpenRouter API key (server only)' -AsSecureString
$env:OPENROUTER_API_KEY = [System.Net.NetworkCredential]::new('', $secureKey).Password
Remove-Variable secureKey
# DATABASE_URL is loaded from the root .env, or set it in this terminal.
& $Python -B -m uvicorn backend.main:create_production_app --factory --host 127.0.0.1 --port 8000
```

120 seconds accommodates two provider timeouts plus retrieval/map work. The
existing gate cannot cancel a running worker on HTTP timeout; do not rapidly retry
a timed-out paid turn. This limitation is unchanged.

## Start frontend — PowerShell terminal 2

```powershell
Set-Location 'src/frontend'
$env:BACKEND_URL = 'http://127.0.0.1:8000'
# Dependencies were installed and the build/lint checks passed during integration.
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
```

Open `http://127.0.0.1:3000` and keep that hostname throughout the session. Select
a location before searching. The browser sends only preferences/messages to its
own `/api` origin. Never put OPENROUTER_API_KEY in frontend files or NEXT_PUBLIC_*
variables. The existing frontend still owns explicit preference edits; a page
reload starts with its existing empty browser snapshot behavior. Cross-reload
preference restoration is not added by this integration.

## Small manual smoke through the frontend proxy

These commands are for the person running the test; **the third request may cost
money**. No such call was executed during integration. The PowerShell cookie jar
is separate from the browser's; use the web checklist below for browser continuity.

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/ready'
$webSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$formTurn = @{ form = @{ food = 'ramen'; budget_max = 100000; location = @{ lat = 10.77; lon = 106.69 } } } | ConvertTo-Json -Depth 8
$first = Invoke-RestMethod 'http://127.0.0.1:3000/api/search' -Method Post -ContentType 'application/json; charset=utf-8' -WebSession $webSession -Body ([Text.Encoding]::UTF8.GetBytes($formTurn))
$budgetTurn = @{ message = 'dưới 80k' } | ConvertTo-Json
$second = Invoke-RestMethod 'http://127.0.0.1:3000/api/search' -Method Post -ContentType 'application/json; charset=utf-8' -WebSession $webSession -Body ([Text.Encoding]::UTF8.GetBytes($budgetTurn))
if ($first.session_id -ne $second.session_id -or $second.state.hard_constraints.budget_max -ne 80000) { throw 'State continuity failed' }
# Explicit paid smoke: use an unparsed dish request so the Rule-only path cannot satisfy the test.
$cloudTurn = @{ message = 'Mình muốn ăn bún riêu chay, không dùng nước hầm xương.' } | ConvertTo-Json
$third = Invoke-RestMethod 'http://127.0.0.1:3000/api/search' -Method Post -ContentType 'application/json; charset=utf-8' -WebSession $webSession -Body ([Text.Encoding]::UTF8.GetBytes($cloudTurn))
$third | Select-Object session_id, clarification_required, state
```

## Browser checklist

1. Select a location. Ask `Mình muốn ăn bún riêu chay, không dùng nước hầm xương.`
   Check extracted food/diet and the server log for an actual primary-model call.
   A rule-only response is not evidence that a paid model worked.
2. Set an absolute budget (`dưới 100k`, then `dưới 80k`). Check food, location and
   unrelated preferences persist. `rẻ hơn` is a relative event and must not invent
   a numeric budget reduction.
3. Add `Mình dị ứng sữa và đậu phộng`. Check both exclusions remain after a budget
   or Wi-Fi update. Unsupported/unverifiable downstream allergy filtering must
   produce a safe constraint error; do not interpret it as verified safe food.
4. With both allergies in state, request `Không còn dị ứng sữa nữa`. Check only milk
   is removed. A vague `Bỏ dị ứng đi` should preserve state and ask for clarification.
5. Repeat several turns without resetting; check the same anon_id/session_id.
   Reset using the existing UI and verify the next conversation starts cleanly.
6. Verify primary/backup behavior with the controlled test below. If both fail,
   require clarification, unchanged state, no results and no map pins. Check a
   malformed request returns the normal sanitized error envelope.

Inspect only server-side diagnostics:

```powershell
Set-Location '.'
Get-Content logs/web-ai2-smoke.jsonl -Tail 8 | ForEach-Object { $_ | ConvertFrom-Json } |
    Select-Object session_id, parser_used, provider_models, provider_errors, fallback_used, state_preserved, clarification_required
```

For a controlled **web** failover test, stop terminal 1's backend with Ctrl+C.
In that same configured terminal, run this temporary process instead. It injects
a primary timeout before any primary network call; GPT backup remains real and
may be billed when you submit an unparsed web request. It changes no source file,
model choice, prompt or router. Do not use reload/multiple workers for this probe.

```powershell
$failoverProbe = @'
from unittest.mock import patch
import uvicorn
from conversation.providers.base import ProviderError
with patch("conversation.parser.create_provider", side_effect=ProviderError("Manual smoke primary timeout", code="timeout")):
    uvicorn.run("backend.main:create_production_app", factory=True, host="127.0.0.1", port=8000)
'@
$failoverProbe | & $Python -B -
```

Submit the same unparsed message in the browser. Confirm fallback_used=true and
the backup model in diagnostics, with an accepted update or a safe clarification.
This tests a simulated primary failure plus a real backup, not an observed Gemini
outage. Stop this process and restart the normal backend to restore primary use.
Offline HTTP tests cover real provider timeout/401/429 classifications and failure
of both providers without any paid calls.

## Select local V3 or V4

Stop the backend first. In terminal 1, set these before the normal uvicorn command:

```powershell
$env:LLM_PROVIDER = 'none'
$env:LOCAL_SLM_ENABLED = 'true'
$env:LOCAL_SLM_BACKEND = 'qwen_lora'
$env:LOCAL_SLM_ADAPTER_VERSION = 'v3' # change to v4 for experimental V4
Remove-Item Env:LOCAL_SLM_ADAPTER_PATH -ErrorAction SilentlyContinue
# If .env contains an explicit path, remove that setting or override it explicitly:
# $env:LOCAL_SLM_ADAPTER_PATH = "$PWD\models\ai2\best_adapter_v4_experimental"
$env:LOCAL_SLM_LOCAL_FILES_ONLY = 'true'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:BACKEND_AI_CONCURRENCY = '1'
$env:BACKEND_AI_TIMEOUT_S = '240'
& $Python -B -m uvicorn backend.main:create_production_app --factory --host 127.0.0.1 --port 8000
```

Use an unparsed turn to exercise local inference. Restart between versions to
release VRAM. `openrouter_chain` intentionally bypasses local inference even if
LOCAL_SLM_ENABLED is true. Restore terminal 1's cloud settings to test the chain.

Repeatable local probes (no downloads, cloud calls or training), one process each:

```powershell
& $Python -B scripts/smoke_ai2_local.py --version v3 --run-model --output logs/new-local-v3.json
& $Python -B scripts/smoke_ai2_local.py --version v4 --run-model --output logs/new-local-v4.json
```

## Verification evidence

Initial targeted backend/AI2 regression: **721 passed, 23 skipped**. Additional
real-AI2/mocked-HTTP boundary tests: **7 passed**. Frontend `npm.cmd run build` and
`npm.cmd run lint` passed. Offline integration demo passed with real AI2 and
explicitly synthetic AI1/AI3. Both actual cache-only Qwen GPU probes passed.

The initial bare full-suite attempt reported **1,701 passed, 31 skipped, 10 failed,
6 errors**: one missing AI1 artifact smoke test and the remaining failures/errors
from sealed-benchmark readers. Use the required sealed guard, as in docs/setup.md.
No historical benchmark data or labels were rewritten to make this run pass.

Final guarded artifact-free suite: **1,705 passed, 49 skipped in 102.57 seconds**.
The offline integration demo was rerun successfully after that suite. Evidence is in
`logs/ai2-fullstack-integration/available-suite.txt` and `available-suite.xml`.
It explicitly excludes `tests/test_ai2_ai1_smoke.py`; rerun that test after the
matching AI1 data is provisioned. Commands:

```powershell
& $Python -B -m pytest -q -p scripts.sealed_benchmark_guard --ignore=tests/test_ai2_ai1_smoke.py
& $Python -B examples/integration_demo.py
```

Transfer/integrity manifests and Qwen reports are in the same ignored local log
directory. Source checkout contents and Git status, plus protected target code and
artifacts, are compared with the pre-transfer snapshot. No Git pull, merge, stage,
commit, push, data/model training or paid API run was performed.
