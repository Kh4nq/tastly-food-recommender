# Fullstack sync and search correctness — 2026-10-15

## Synchronization

Fetched `origin` and fast-forwarded `ai2-integration-local` from
`a7df3bac928df26d551f6c2ad56311828aeebf2a` to
`eda2b8ccf4987a76e2cbb18e9bd68f4ddf29d1a8`. Incoming commits:

- `17c1671`: sweep expired auth sessions on sign-in, tests, backend task notes,
  and remove upstream's tracked junk file `adsadasdas`.
- `eda2b8c`: keep the existing map mounted/visible during search loading; hide
  stale cards under the card skeleton (`SearchResult`, `SearchLoading`,
  `ResultExplorer`).

No incoming AI1, AI2, AI3, shared-schema, dependency or MapView changes. Incoming
paths did not overlap dirty/untracked local files. All pre-existing changes were
preserved; the pre-sync snapshot is under ignored
`logs/fullstack-sync-20261015/files`, with `local.patch` and `manifest.json`.
The large untracked data ZIP was hashed and retained in place. No stash, reset,
new commit or push was used. The original source checkout was not edited.

## Trace and causes

Both chat and form use `SearchPreferenceProvider` and `buildSearchRequest`.
They send one `preference_state`; old absolute form fields are not replayed on
chat turns. The cookie supplies server identity. `SearchService` passes the
effective snapshot to AI2, retrieves/ranks only accepted search/refinement turns,
and saves after successful retrieval. Conversational/provider-failure turns
preserve stored state and skip retrieval. AI3 preserves candidate identities;
the presenter joins display data by menu ID and preserves rank order.

**Bug A had three contributing gaps.** The LLM-first acceptance path could accept
a vegetarian dish request without `hard_constraints.vegetarian=true`. AI1's
existing vegetarian filter correctly excludes nonvegetarian/unknown dishes when
that flag is present. Its contiguous-phrase matcher missed `Phở nấm chay` for
`phở chay`. Finally, named-food retrieval retained zero-match rows for CatBoost,
which could rank unrelated dishes. This was not corrected by sorting UI cards.

An offline probe of the existing 26,025 restaurants / 4,068 dishes / 173,546 menu
rows at `(10.7769, 106.7009)` with 100k/3km found 10,307 eligible rows without the
vegetarian flag, 6,215 with it, but zero contiguous `phở chay` matches in either
case. The qualified name was missed. Menu IDs were unique; repeated restaurants
are allowed menu-level recommendations, not duplicate menu identities.
Running the original tracked retrieval implementation and real CatBoost on that
same state reproduced ten `Gỏi cuốn tôm` results, with zero positive food matches
among its 100 candidates. The repaired path returns matching vegetarian pho.

**Bug B was a scope mismatch.** The extensible AI2 hard-constraint container
accepted `transport_mode`. AI1 correctly rejected that unknown hard key even
though transportation already has a supported context field. A car does not
establish a parking requirement.

## Targeted changes

| File | Behavior |
| --- | --- |
| `src/conversation/search_contract.py` | After semantic interpretation, move only transport from hard/soft containers to canonical context; reject conflicts; ensure explicit vegetarian requests bind the diet; preserve the explicitly requested `chén trứng` side as unverified context, not an alternative main dish. Mandatory unverified sides clarify. |
| `src/conversation/llm_first.py` | Apply that repair before existing safety acceptance and to form-only updates. No extra provider call or intent component. |
| `src/conversation/safety.py` | Ground accompaniment strings in positive current-message evidence, recognize English car/bicycle context, honor explicit vegetarian form food. Existing numeric/allergy/identity/reference checks remain. |
| `src/conversation/prompts.py` | State the existing transport/diet/side contract explicitly; retain model selection and architecture. |
| `src/retrieval/retriever.py` | Qualified names containing all query words in order score 0.85, not exact 1.0. Named-food searches exclude lexical misses before Top-K and ranking; absence returns empty. Map lookup reuses the same matcher. |
| `src/backend/api/routes_search.py` | Add natural warnings for unverified sides and geographic rather than routed travel distance. No API-schema changes. |
| `src/frontend/components/chat/ChatWidget.tsx` | Display existing response warnings in the bot bubble; preserve styling. |
| `src/frontend/components/search/SearchPreferenceProvider.tsx` | Cancel in-flight searches when the selected coordinates change; discard results for the old origin. Existing version/abort checks for searches/form edits remain. |
| `tests/backend/test_search_correctness.py` | Authored offline AI2, actual AI1/CatBoost, hard-filter, Top-K survival, HTTP/presenter/map, form, rollback and unverified-side regressions. |

LLM-first Gemini → GPT → opt-in cache-only Qwen V4 remains intact. Standalone
V3/V4 selection, adapter paths/loading/dependencies are preserved. No retraining,
weights, dataset, database, embeddings, AI3 algorithm, shared schemas or map
implementation were changed. No supplementary Top-K section/policy or LLM
explanation was implemented. Strict unsupported mandatory constraints still fail.

## Reproduce offline verification

Final full guarded suite: **1,782 passed, 49 skipped**, zero failures
(101.24 seconds). Focused backend/retrieval/session suite before the final two
additional form/diet cases: **328 passed, 23 skipped**; those extra cases passed
in the full run. The integration demo passed after the full suite. Frontend
lint and production build, including TypeScript, passed. The first sandboxed
build hit `spawn EPERM` at its TypeScript worker; the permitted rerun passed.

Skipped: 23 PostgreSQL tests without `TEST_DATABASE_URL`, 18 sealed-benchmark
tests deliberately excluded by the guard, seven legacy OpenAI-SDK tests because
that optional package is absent, and one collection-level skip. No new dependency
was installed. Normal offline provider guards remain active. Protected SHA256
verification found zero changes in 55 checked environment/data/model/common/DB/
ranking/test-fixture/dependency files, including both V3/V4 adapter weights and
the untracked ZIP. Reports: `logs/fullstack-sync-20261015/full-suite.xml`,
`focused.xml`, `integration-demo.txt`, `integrity.json`.

```powershell
Set-Location '.'
$Python = '.\.venv\Scripts\python.exe'
$env:PYTHONPATH = "$PWD\src;$PWD"
$env:PYTHONDONTWRITEBYTECODE = '1'
& $Python -B -m pytest -q -p scripts.sealed_benchmark_guard tests/backend tests/test_llm_first.py tests/test_retrieval_retriever.py tests/test_retrieval_hard_filter.py tests/test_retrieval_map_places.py tests/test_ai1_ai3_integration.py tests/test_ai2_ai1_smoke.py
& $Python -B -m pytest -q -p scripts.sealed_benchmark_guard
& $Python -B examples/integration_demo.py
Push-Location src/frontend
npm.cmd run lint
npm.cmd run build
Pop-Location
```

The real-data authored diagnostic in
`logs/fullstack-sync-20261015/real_search.py` mocks the cloud turn only, blocks
network sockets, loads the cached embedding model on CPU, runs actual filtering,
retrieval, CatBoost and map lookup, and checks deterministic repetition. Its
100 retrieved candidates / 10 ranked results all reference `Phở nấm chay`, with
verified dataset vegetarian flags and within budget/distance; 100 matching map
restaurants. Output: `real-search.json`. These local data include existing demo
records and estimated prices; this is structural correctness, not verified real
restaurant/menu availability or quality evidence.

## Start the application

Backend, terminal 1 (existing root `.env` supplies server secrets/DATABASE_URL;
PostgreSQL must already be running):

```powershell
Set-Location '.'
$Python = '.\.venv\Scripts\python.exe'
$env:PYTHONPATH = "$PWD\src;$PWD"
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:LLM_PROVIDER = 'openrouter_chain'
$env:OPENROUTER_ENABLED = 'true'
$env:AI2_LLM_FIRST_ENABLED = 'true'
$env:BACKEND_AI_TIMEOUT_S = '120'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
& $Python -B -m uvicorn backend.main:create_production_app --factory --host 127.0.0.1 --port 8000
```

Optional local final fallback: before starting backend, set
`LOCAL_SLM_ENABLED=true`, `BACKEND_AI_CONCURRENCY=1`,
`BACKEND_AI_TIMEOUT_S=240`. Existing V4 adapter/cache/GPU must be available.
Cloud failures are still attempted first. Default local enablement stays opt-in.

Frontend, terminal 2:

```powershell
Set-Location 'src/frontend'
$env:BACKEND_URL = 'http://127.0.0.1:8000'
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
```

Open `http://127.0.0.1:3000`. All natural-language turns in this mode may incur
OpenRouter charges. No live paid call was made during this task. Keep credentials
server-side; never use `NEXT_PUBLIC_OPENROUTER_API_KEY`.

Optional manual API smoke through the same frontend proxy (may incur charges;
its cookie jar is separate from the browser):

```powershell
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$body = @{ message = 'Phở chay dưới 100k cách tôi 3km'; form = @{ location = @{lat=10.7769;lon=106.7009} }; include_map_places=$true } | ConvertTo-Json -Depth 8
$first = Invoke-RestMethod 'http://127.0.0.1:3000/api/search' -Method Post -ContentType 'application/json; charset=utf-8' -WebSession $session -Body ([Text.Encoding]::UTF8.GetBytes($body))
$first | Select-Object state,results,warnings
$body = @{ message='Đổi ngân sách tối đa 80k' } | ConvertTo-Json
$next = Invoke-RestMethod 'http://127.0.0.1:3000/api/search' -Method Post -ContentType 'application/json; charset=utf-8' -WebSession $session -Body ([Text.Encoding]::UTF8.GetBytes($body))
if ($first.session_id -ne $next.session_id -or $next.state.hard_constraints.budget_max -ne 80000) { throw 'State continuity failed' }
```

## Manual web checks still required

1. Select an origin; send both vegetarian-pho phrases. Check food, vegetarian,
   100k/3km state and actual payload/card/menu/map identities. No meat dishes or
   unrelated vegetarian dishes; an honest empty list is valid where absent.
2. Change to 80k, then ask `Tôi muốn quán yên tĩnh hơn`. Check food, vegetarian,
   distance and budget persist, and quietness remains soft. Check the form agrees.
3. Reset, send the full car/egg query. Expect main food `phở tái`, side in context,
   car in context, 10km, no inferred mandatory parking, an unverified-side warning
   and a geographic-distance notice. Do not assume the side is available.
4. Reset; try `Tìm ramen dưới 150k trong 3km`, then
   `Phở khác bún như thế nào?` and `Chào bạn`. Questions/greetings must preserve
   results/state and make no retrieval request inside the backend pipeline.
5. Add an allergy, change budget/ambience, and inspect retained exclusions.
   AI1 currently cannot verify every mandatory allergy; an actionable error must
   not be interpreted as a verified allergy-safe recommendation.
6. Delay a response with browser network throttling; submit a newer search/form
   edit or change origin. The old response must not replace newer state/results.
   Confirm the upstream map remains visible while cards load.
7. Verify real Gemini, then simulate primary failure in a separate manually
   started test backend by patching `conversation.llm_first.create_provider` to
   raise `ProviderError`; GPT should handle the single turn. Patch
   `create_chain_provider` too, with local enabled, to verify the V4 final path.
   Use restart-scoped test patches; never change credentials or production code.
   These manual cloud/GPU tests were not run in this task.

Live Gemini/GPT schema/latency/failover, visual browser interaction, and
PostgreSQL-to-Parquet display parity remain unverified. No production-readiness
claim is made. Lexical matching deliberately prefers honest empty results for
unrecognized translations/synonyms; expanding food ontology is separate work.
Review those boundaries before future supplementary Top-K / grounded explanations.
