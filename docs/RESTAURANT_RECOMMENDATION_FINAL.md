# Final restaurant recommendation integration

## Resulting behavior

Hard filters → dish-only food/semantic evidence → bounded primary/alternative
menu pools → existing CatBoost scores → restaurant grouping → primary-first
restaurant Top-K → existing cards/map. Post-ranking explanations have been removed;
see [current budget/chat handoff](AI2_BUDGET_CHAT_FINAL.md).

Previously lexical misses were discarded before alternative selection, and
menu-level Top-K preceded grouping. A prolific restaurant could fill the list.
Both problems are addressed without changing AI2 extraction, hard-filter policy,
CatBoost weights/features order, datasets, embeddings or map providers.

## Retrieval and ranking

Food matching folds accents and case, respects token boundaries, recognizes
qualified/reordered dish names and protects against unrelated product heads
(including phô mai versus phở). Exact=1.0, prefix=.95, phrase=.9, qualified or
reordered=.85. `phở tái` matches `phở bò tái`; `phở bò`/`phở gà` remain zero-score
alternatives, never exact matches. `phở chay` matches `phở nấm chay`.

Alternatives require independently grounded dish-family evidence AND dish cosine
>=.25. This is a conservative heuristic, not a calibrated quality claim. Cakes,
smoothies and unrelated fast food do not qualify merely through a restaurant
embedding. Unknown food families get honest empties rather than guesses. Both
pools go through identical budget/distance/vegetarian/facility filtering; unsupported
mandatory allergy or other constraints still fail closed. Car remains AI2 context.

The pre-existing restaurant vectors include names. AI1 neutralizes their similarity
to 0 and forwards dish-only semantic similarity, so arbitrary synthetic brands
cannot influence retrieval or CatBoost features. The 15-feature schema and trained
model are unchanged; no artifact was regenerated. Ranking quality is not established
by these structural tests and needs future evaluation of this feature adaptation.

Retrieval selects menus in rounds across distinct IDs, reserving room for direct
matches and alternatives. It does not discard every extra dish at a venue. A known
matching venue outside the primary slice cannot sneak back as supplementary-only.
Web retrieval requests max(configured retrieval_top_k, 4*K), capped at 1,000; the
default is 100. All retained menus reach AI3. Bounded preselection is not exhaustive
global ranking; eligible-menu lists contain the retrieved eligible slice.

Grouping uses `restaurant_id`, never names. Its representative is the strongest
AI3-scored direct menu if any exists; otherwise the strongest qualified alternative.
Equal scores use restaurant/menu/dish IDs. Original candidate ranks, scores, menu
IDs, dish IDs, food scores and evidence remain in `eligible_menu_items` and
`reason_features`. Duplicate/unknown ranker identities fail loudly.

Select up to K primary restaurants, then only enough supplementary restaurants to
fill unused slots. Never fill with unrelated dishes. With no meaningful food query,
results are `general`, not supplementary. Older injected retrievers lacking optional
food evidence retain general-result compatibility without claiming direct matches.

## Web contract and UI

`POST /api/search` keeps its request and existing result fields. `results` now has
one representative menu per restaurant; `top_k` counts unique restaurants. All
restaurant/menu/dish IDs retain source semantics. Additions per result:

- `recommendation_group`: primary, supplementary or general.
- `food_match`, `candidate_rank`, `reason_features`: original evidence.
- `eligible_menu_items`: canonical RankedResult entries, original candidate ranks.
- `explanation`, `explanation_source`: retired nullable compatibility fields.
- `catalog_only=true`: these are demo catalog records.

Response-level `named_food_query` distinguishes named-dish UI from general mode.
Favorites still use restaurant IDs and representative fields. The separate Today
recommendations endpoint and account/navigation contracts are unchanged.

Named searches show **Kết quả phù hợp** before **Gợi ý thêm**, with English
translations. The alternative heading is absent when unused. A friendly notice
appears when only alternatives exist. Cards retain their actions, price, distance,
rating and responsive layout. Eligible additional menus use compact details;
alternative dishes remain labeled. Cards do not display explanation paragraphs.
A visible synthetic-catalog notice qualifies menus/prices/availability.

The existing map still shows all matching places independently of Top-K; selected
supplementary venues are added using their filtered source coordinates. Backend
and UI deduplicate by restaurant ID. Selected representatives supply their correct
menu/price/coordinates for highlighted pins. Existing map loading stays mounted;
matching pins outside card Top-K retain their earlier no-card-selection behavior.

The search input is already controlled by `filterValues(preferences).dish`; there
is no independent truncated food label. It uses the accepted response state.
Regression tests preserve `phở chay` exactly and ensure chat does not replay stale
absolute form values. Explicit edits/new searches/origin changes retain existing
abort/version safeguards; no extraction rewrite or new intent router was added.

## Post-ranking explanations removed

Search ends after grouping, Top-K selection and normal response projection. There
is no explanation provider request, deterministic explanation text or card paragraph.
The old `BACKEND_EXPLANATION_*` settings are unused and have been removed from the
environment example. Compatibility response fields remain null. AI2 conversation
calls retain their existing Gemini → GPT → opt-in Qwen V4 chain.

## Changed files

| Files | Reason |
| --- | --- |
| `src/retrieval/food_matching.py`, `src/retrieval/retriever.py` | Dish normalization, qualified alternatives, bounded diverse pools, name-neutral features |
| `src/pipeline/selection.py`, `src/pipeline/recommend.py`, `src/backend/services/pipeline.py` | Shared post-AI3 grouping and restaurant Top-K |
| `src/backend/services/search_service.py`, `src/backend/wiring.py` | Preserve map contract, add selected alternative pins, preserve the existing search service wiring |
| `src/backend/services/explanations.py` (removed), `src/conversation/providers/openrouter_provider.py` | Retire explanations and their unused structured transport helper; preserve conversation profiles |
| `src/backend/api/schemas.py`, `presenter.py`, `routes_search.py` | Additive view fields, original eligible-menu projection and named-query flag |
| `src/frontend/lib/api.ts`, `search-results.ts`, `locales/vi.ts`, `locales/en.ts` | Typed groups, stable ID/map helpers, localized sections and catalog notice |
| `src/frontend/components/search/ResultExplorer.tsx`, `SearchResult.tsx` | Group sections, one card per restaurant, menu details and disclaimer |
| `.env.example` | Remove obsolete explanation settings; actual .env remains untouched |
| `tests/test_restaurant_selection.py`, `test_retrieval_food_pools.py` | Top-K/grouping/ties/name invariance/constraints/relevance/diversity |
| `tests/backend/test_grouped_search_integration.py` | Full offline response contract and no post-ranking provider calls; obsolete explanation tests removed |
| `src/frontend/tests/search-contract.test.mjs` | Grouping/map/state helpers through existing TypeScript compiler and Node runner |
| `tests/test_pipeline_mock.py`, `test_ai1_ai3_integration.py`, `test_ai2_ai1_smoke.py`, `tests/conftest.py` | Updated scoring-before-grouping expectations, name-neutral feature expectations, isolated test environment |
| This document, `docs/integration_contract.md`, `ai1_retrieval.md`, `ai3_ranking.md`, `AI2_LLM_FIRST.md` | Contract/ownership handoff and reproducible commands |

## Reproduce offline verification

Prior recommendation-stage verification (before explanation removal; current results are in the budget/chat handoff):

Guarded full suite: **1,832 passed, 49 skipped, zero failures** (113.50s).
Focused backend/retrieval/ranking/contract suite: **328 passed, 23 skipped**.
Offline integration demo passed after the full suite. Node frontend contract
tests: **4 passed**. ESLint and the Next.js production build, including TypeScript,
passed. Sandbox `spawn EPERM` worker errors were resolved by permitted reruns.

Skipped: 23 PostgreSQL tests without `TEST_DATABASE_URL`, 18 sealed-benchmark
readers deliberately guarded, seven optional legacy OpenAI-SDK tests (SDK absent),
and one collection-level skip. No dependency was installed to change those skips.
Provider calls in tests are mocked and offline network guards remain active.

The cache-only real-data probe ran existing embeddings and CatBoost at
`(10.7769,106.7009)`: vegetarian pho returned ten unique primary restaurants;
pho tai/10km had no direct match and returned ten qualified supplementary
restaurants, with no explanations; general pho returned ten unique primary
restaurants. The primary scenarios used one mocked batch each for three IDs.
Ranking repeated deterministically and all map IDs were unique. Those observations
describe this synthetic catalog/location, not real menu availability or quality.

Evidence is under ignored `logs/restaurant-final-20261015/`: `focused.xml`,
`full-suite.xml`, `integration-demo.txt`, `real-catalog.json`, `integrity.json`.
A pre-edit snapshot (`before.json` plus `files/`) preserves all 81 prior dirty or
untracked paths, with the large ZIP retained in place. Hash verification found
zero changes among 54 checked environment/data/model/common/DB/ranking/dependency/
fixture files. No Git synchronization, commit, reset or push occurred in this task.

```powershell
Set-Location '.'
$Python = '.\.venv\Scripts\python.exe'
$env:PYTHONPATH = "$PWD\src;$PWD"
$env:PYTHONDONTWRITEBYTECODE = '1'
& $Python -B -m pytest -q -p scripts.sealed_benchmark_guard tests/backend tests/test_restaurant_selection.py tests/test_retrieval_food_pools.py tests/test_pipeline_mock.py tests/test_ai1_ai3_integration.py tests/test_ai2_ai1_smoke.py tests/test_openrouter_provider.py
& $Python -B -m pytest -q -p scripts.sealed_benchmark_guard
& $Python -B examples/integration_demo.py
Push-Location src/frontend
node --test tests/search-contract.test.mjs
npm.cmd run lint
npm.cmd run build
Pop-Location
```

## Manual startup and acceptance

Backend terminal (existing root .env supplies DATABASE_URL and server credentials;
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

Frontend terminal:

```powershell
Set-Location 'src/frontend'
$env:BACKEND_URL = 'http://127.0.0.1:8000'
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
```

Open `http://127.0.0.1:3000`. Natural-language conversation calls may cost money
for AI2 intent understanding and conversation. No paid call was run by the implementation agent.
Keep OPENROUTER_API_KEY out of frontend/NEXT_PUBLIC variables.

Manual API smoke via the frontend proxy (separate cookie jar from the browser):

```powershell
$webSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$body = @{message='Phở chay dưới 100k cách tôi 3km';form=@{location=@{lat=10.7769;lon=106.7009}};top_k=10;include_map_places=$true} | ConvertTo-Json -Depth 8
$r = Invoke-RestMethod 'http://127.0.0.1:3000/api/search' -Method Post -ContentType 'application/json; charset=utf-8' -WebSession $webSession -Body ([Text.Encoding]::UTF8.GetBytes($body))
$r.results | Select-Object restaurant_id,menu_item_id,dish_name,price_vnd,recommendation_group,food_match,explanation
if (@($r.results.restaurant_id | Select-Object -Unique).Count -ne $r.results.Count) { throw 'Duplicate restaurants' }
$body = @{message='Phở khác bún như thế nào?'} | ConvertTo-Json
$chat = Invoke-RestMethod 'http://127.0.0.1:3000/api/search' -Method Post -ContentType 'application/json; charset=utf-8' -WebSession $webSession -Body ([Text.Encoding]::UTF8.GetBytes($body))
if ($chat.results.Count -ne 0 -or $chat.intent -ne 'informational') { throw 'Conversation routing failed' }
```

Browser checklist (reset between unrelated food scenarios so a vegetarian/allergy
constraint is not silently removed):

1. Vegetarian pho, 100k/3km: exact effective food in form, mandatory vegetarian,
   unique restaurant cards, matching dishes first, alternatives labeled, no meat.
2. Pho tai/car/10km: tai variants primary; other qualifying pho only supplementary;
   geographical distance and no inferred mandatory parking.
3. Pho tai with chén trứng: retain unverified side context and warning; never claim
   the restaurant can actually supply eggs. Mandatory unsupported sides clarify.
4. General pho: multiple eligible menus expand under one card; K counts venues.
5. Pho-versus-bun question/greeting: natural reply, old state/results preserved,
   no retrieval/ranking/explanation.
6. Budget/quietness/allergy refinement: preserve independent constraints; unsupported
   mandatory allergies fail closed. Form/chat fields agree. Throttle a response,
   then edit/search/change location: stale responses must not overwrite new state.
7. Cards contain no explanation paragraphs. Confirm there are no post-ranking
   provider calls or calls on rerender, expansion, hover or map selection.

Live Gemini/GPT latency and schema acceptance, visual browser behavior,
and PostgreSQL/Parquet display parity remain manual validation. This is not a
production-readiness or retrieval-quality claim. Source data, weights, embeddings,
credentials, benchmarks and Qwen V3/V4 loading/selection remain preserved.
