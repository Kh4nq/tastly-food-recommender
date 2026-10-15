# Final AI2 budget and chat fixes — 2026-10-15

## Behavior

The LLM-first provider chain still interprets each message. Numeric grounding used
to require an explicit currency/scale unit, so a correct model delta for
`tìm phở dưới 100000` failed validation and could exhaust both cloud providers.
Grounding now accepts whole unitless VND literals with local budget/price wording,
or a clear bound/reduction in food-search context. Grouped thousands and sentence
punctuation work; `100k`, `100.000đ`, `100000 VND` and English VND expressions remain
supported. This validates the model's amount; it does not parse intent first.

Bare numbers, small ambiguous shorthand, nearby counts/distances/times/IDs,
foreign-currency suffixes, negated amounts and ambiguous unitless ranges are not
converted to VND. Bounds cannot switch minimum/maximum dimensions. Existing form
authority, coordinates, session ownership, allergy preservation and rollback checks
remain in place. Monetary shorthand without sufficient context still clarifies.

ChatWidget uses a deterministic localized search-status reply:

| Accepted response | Reply |
| --- | --- |
| Primary restaurants | Actual unique primary count, qualified as demo catalog data |
| General/legacy recommendations | Actual unique count without claiming an exact dish match |
| Supplementary only | No direct match; actual unique alternative count |
| Completed empty search | No suitable catalog results; suggest changing dish/distance |
| Clarification | Ask for a simpler dish, maximum budget or distance, with an example |
| Deferred/location pending | Ask for the search origin; do not claim an empty search |
| Informational/conversational | Preserve the existing AI2-generated reply |

Unverified accompaniments and allergy warnings take priority over other warnings.
Repeated technical result warnings stay on the results page. Chat warnings are
deduplicated and bounded (at most two, 300 characters each). Request errors and
stale/aborted responses keep the existing error/version handling. The search
provider, form/chat synchronization, location flow, retrieval, ranking, grouping
and map code have not been changed.

## Explanation removal

Search ends after AI3, existing restaurant grouping/Top-K and response projection.
There is no post-ranking LLM request, explanation cache, deterministic explanation
generator or explanation paragraph on cards. AI2 calls for interpretation and
normal conversation remain. Obsolete `BACKEND_EXPLANATION_*` variables are inert;
their example configuration and test-environment wiring were removed. Actual
environment files were not edited. Optional response fields `explanation` and
`explanation_source` retain their previous nullable types and return null.
Ranking scores, `reason_features`, eligible additional menus and catalog notices
remain available. Older cached explanation text is ignored by cards.

## Files changed

| Files | Reason |
| --- | --- |
| `src/conversation/grounding.py`, `src/conversation/safety.py`, `src/conversation/evidence.py` | Contextual unitless VND validation and absolute cheaper-budget evidence |
| `src/frontend/lib/chat-response.ts` (new) | Deterministic result-aware localized replies and bounded warnings |
| `src/frontend/components/chat/ChatWidget.tsx` | Use response helper; existing pending-location bubble uses the new wording |
| `src/frontend/lib/locales/vi.ts`, `src/frontend/lib/locales/en.ts` | Vietnamese/English search-status messages |
| `src/backend/services/explanations.py` (deleted) | Remove provider requests, cache and deterministic explanation generation |
| `src/backend/services/search_service.py`, `src/backend/wiring.py` | Remove explanation invocation and dependency wiring |
| `src/conversation/providers/openrouter_provider.py` | Remove the explanation-only generic completion helper, retain conversation transport |
| `src/backend/api/presenter.py` | Stop projecting explanation text |
| `src/backend/api/schemas.py`, `src/frontend/lib/api.ts` | Document retained compatibility fields |
| `src/frontend/components/search/ResultExplorer.tsx` | Remove explanation paragraph only |
| `.env.example`, `tests/conftest.py` | Remove obsolete explanation configuration/isolation |
| `tests/test_unitless_budgets.py` (new) | Units, dimensions, punctuation, state preservation, form authority and failover |
| `tests/backend/test_grouped_search_integration.py` | Real offline AI1/CatBoost/grouping/API contract; reject any post-AI2 provider request |
| `tests/backend/test_explanations.py` (deleted) | Retire tests for the removed feature |
| `src/frontend/tests/chat-response.test.mjs` (new) | Reply branches, counts, warnings and actual card rendering without explanation paragraphs |
| This document, `docs/AI2_LLM_FIRST.md`, `docs/integration_contract.md`, `docs/RESTAURANT_RECOMMENDATION_FINAL.md` | Current contract, removal and verification handoff |

## Offline verification

Commands use the already-installed Python 3.11 environment without modifying it.
No package installation, model training/download or paid API call is needed.

```powershell
Set-Location '.'
$Python = '.\.venv\Scripts\python.exe'
$env:PYTHONPATH = "$PWD\src;$PWD"
$env:PYTHONDONTWRITEBYTECODE = '1'
& $Python -B -m pytest -q -p scripts.sealed_benchmark_guard tests/backend tests/test_unitless_budgets.py tests/test_llm_first.py tests/test_openrouter_provider.py tests/test_ai2_safety_patch.py
& $Python -B -m pytest -q -p scripts.sealed_benchmark_guard
& $Python -B examples/integration_demo.py
Push-Location src/frontend
node --test tests/search-contract.test.mjs tests/chat-response.test.mjs
npm.cmd run lint
node node_modules/typescript/bin/tsc --noEmit --incremental false
npm.cmd run build
Pop-Location
```

Final verification:

- Focused backend/AI2/provider suite: **375 passed, 23 skipped**.
- New unitless-budget tests: **37 passed**.
- Full guarded Python suite: **1,852 passed, 49 skipped**, no failures (125.34s).
- Offline integration demo: **passed**, after the full suite.
- Frontend contract/chat/card tests: **19 passed**.
- ESLint, explicit TypeScript `--noEmit` and Next.js production build: **passed**.
- **66 protected-file hashes unchanged**, including environment/data/model files,
  AI1/AI3/grouping contracts and form/chat/location/map synchronization code.

Skipped checks: 23 PostgreSQL cases without `TEST_DATABASE_URL`, 18 sealed benchmark
readers, seven optional legacy OpenAI-SDK cases and one collection-level skip.
The guard prevents sealed benchmark access; tests retain offline socket guards.
Evidence and hashes are under ignored `logs/budget-chat-final-20261015/`.
Pre-existing data marker deletions and untracked ZIP/manifest remain untouched.
No pull, commit, push or credential/artifact edits were performed.

## Manual acceptance and limits

Use the unchanged backend/frontend startup commands in the recommendation runbook;
there is no explanation feature flag to set. Natural-language AI2 calls may incur
provider charges and were not exercised live during this implementation.

1. Search `tìm phở dưới 100000`; confirm the effective budget is 100000 and chat
   reports the actual unique primary count, or alternatives/empty state honestly.
2. Refine `giảm ngân sách xuống 80000`, then `giảm xuống dưới 150000`; verify food,
   distance, vegetarian/allergy constraints and explicit form priority remain intact.
3. Try `find fried chicken under 100000` and `budget below 150000` in English mode.
4. Search without an origin; chat asks for location while the existing picker is
   pending, then reports the completed response. Change location rapidly to check
   the existing stale-response safeguards.
5. Try supplementary-only and empty searches, a clarification, a greeting and
   `Phở khác bún như thế nào?`. Normal conversation must retain the AI2 reply.
6. Request `chén trứng`; the unverified accompaniment warning must remain visible.
   Cards retain their prices, extra menus, actions, provenance and map selection;
   there must be no repeated explanation paragraph or post-ranking provider call.

Live Gemini/GPT/local Qwen behavior, PostgreSQL-dependent checks when no test DB is
configured, and interactive browser/location behavior remain separate verification.
Automated card rendering and mocked offline integration are not a live web smoke
test or evidence of independently verified restaurant/menu availability.
