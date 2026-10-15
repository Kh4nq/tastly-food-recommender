> Historical development report. Use the [public README](../README.md) and [setup guide](setup.md) for the current distribution.

# AI 2 v0.2 High Audit

## 1. Overall verdict

The 537-test baseline passed when rechecked, but it did not cover several
incorrect merge, validation, safety and observability behaviors. This audit
identified and fixed **18 concrete findings**, with reproducing tests before
each fix. Final verification: **593 passed, 0 failed** (56 added cases).

The architecture remains Rule -> optional Local SLM -> external fallback ->
normalization -> State Manager. No model implementation, training, dependency
installation or provider network change was made. No existing test was weakened
or changed. The workspace has no Git repository, so inspection used the current
files and the verified baseline, rather than a Git diff.

## 2. Concrete findings, causes and fixes

| ID | Finding / exact cause | Fix and regression evidence |
| --- | --- | --- |
| F01 | Hybrid merge applied model dictionaries after rules without protecting explicit numbers. A model could turn `dưới 50k` into 60000. Legacy model `set_values.hard_constraints` could also replace unrelated persistent constraints. | Retain deterministic hard values unless the message contains an unresolved correction of that attribute. Treat legacy model hard/soft replacement containers as per-key deltas. Six regressions cover conflicting budget, distance and travel time in both model output shapes. Direct human/caller replacement semantics remain available. |
| F02 | Unconditional reapplication of rule context/parking prevented a model from interpreting a later correction. `có parking thì tốt nhưng thật ra bắt buộc phải có` stayed soft; a later lunch/taxi correction could stay dinner/motorbike. | Recognize explicit correction markers with attribute-specific evidence. Release that field only when the later correction is still unresolved by rules. Hard/soft conflict normalization then applies. Three regressions cover parking, meal time and transport. The existing spelled-out budget-correction tests still pass. |
| F03 | Normalization dropped redundant soft values before processing removals. Hard wifi + soft wifi + removal of only hard wifi lost both. | Centralize delta-removal cleanup in normalization and run it before hard/soft and absolute/relative cleanup. The scoped hard removal now preserves the soft addition. |
| F04 | All legacy numeric removal keys were unconditionally rewritten as hard paths, even when the key existed only in soft preferences. | Resolve legacy numeric scope against the current state and update. Remove the existing scope; if both exist, remove both deterministically; without scope evidence, retain the historical hard default. Canonical paths stay exact. Two scope regressions added. |
| F05 | Whole food/cuisine removals cleared state but left contradictory set values in the effective update. Explicit forms also failed to override these removals. | Remove the corresponding set entry during normalization and clear matching removals when applying an explicit form. Tests cover both food and cuisine, including form priority. |
| F06 | `validate_assignment` did not validate mutation inside dictionaries. A caller could mutate context_updates after construction to insert location or party_size=0, and State Manager copied it without revalidation. | Revalidate the serialized delta at normalization/state boundaries. Both mutations now fail without changing the caller's object. |
| F07 | Reserved state fields were rejected in hard wire constraints but not soft constraints or all public/context write paths. Legacy `set_values.context` could bypass known context validation. | Share the hard/soft wire entry domain; reject reserved state/query keys in public constraint deltas and context_updates. Validate known fields and reject misplaced state/query fields in legacy context replacements while preserving custom nested legacy context. Regressions cover food/cuisine/location/context and invalid party size. |
| F08 | New structured keys had inconsistent validation across provider and public contracts. Negative travel time/budget_min, min_rating=8, scalar allergen exclusions and string parking were accepted. | One shared known-constraint validator is used by public additions/replacements and wire entries. Unknown valid custom keys remain extensible. Five paired public/wire regressions added. |
| F09 | Allergen list assignment could erase previously stated allergies. Hybrid conversion could also lose exclusions supplied in a model replacement container. | Merge hard allergen additions by ordered union with existing exclusions; preserve both rule and model exclusions. A direct explicit replacement/removal remains possible. Regression verifies milk + peanut + shellfish and explicit replacement separately. |
| F10 | Global filler cleanup removed `chuyển qua`. `ramen chuyển qua sushi` became a confident two-food rule result instead of a replacement request. | Remove the operator from generic filler. Consume it only inside a recognized transport expression. Both food-replacement examples now remain unresolved; the existing transport-switch rule-only case still passes. |
| F11 | The new `không quá xa` rule omitted the negation guard used by other rules. `không cần không quá xa` incorrectly added soft near. | Apply the same scoped negation guard before emitting near. Added a reproducing regression. |
| F12 | SLM result validation defaulted a missing update to an empty update and coerced boolean/string confidence into numeric confidence. Invalid results could bypass external fallback. | Require an explicit update; require strict finite numeric confidence in [0,1] and a strict fallback boolean. The disabled backend explicitly returns an empty update. Three malformed-result regressions verify exactly one external fallback. |
| F13 | slm_called was set before backend construction. An unknown backend reported a call even though no provider existed. | Construct the backend before setting slm_called. Factory failure reports slm_called=false, confidence=null and fallback=true. Added a regression. |
| F14 | The interactive latency projection omitted slm_ms, although the main metadata contained it. | Include slm_ms in the latency display/export metadata projection. Disabled-route display regression verifies zero. |
| F15 | Shared redaction traversed dictionary values but retained keys verbatim. Core logs and benchmark output could expose a credential used as an extensible dictionary key. | Redact keys in the shared recursive utility while retaining numeric usage counters. Interactive redaction continues to use that utility. A synthetic secret-key regression verifies the boundary. |
| F16 | Benchmark subset comparison iterated empty expected dictionaries and produced no checks. An expected empty relative_updates map could therefore accept nonempty events. | Compare nested empty dictionaries explicitly. The root empty expectation remains the existing “no assertions” convention. A targeted evaluator regression now rejects a nonempty relative map. |
| F17 | The readiness checker returned `str(ValidationError)`, which includes raw input values and could echo credentials from malformed datasets. | Return a bounded schema-error description with the line number instead of input-bearing Pydantic text. Added a synthetic secret regression. |
| F18 | Legacy context.relative_updates was purged only after state transition. A loaded old snapshot could still send its stale event into an external or local model on the next turn. | Remove legacy relative events from independent inference-state copies for both routes. Two regressions verify clean model inputs and unchanged caller snapshots. |

## 3. Semantic review

**Relative lifetime.** F18 closes the legacy-input leak. Normal multi-turn
processing, interaction history and current-state rebuilding do not replay the
previous delta. Directions remain in the originating PreferenceUpdate/log only;
no numeric adjustment policy or expiration system was invented.

**Absolute priority.** Rule and hybrid regressions verify 40000/50000 VND, 3km
and 10 minutes without redundant relative events. Unrelated model additions
preserve deterministic values. Existing explicit natural-language corrections
remain supported. F01/F02 address the two opposing merge errors.

**Hard/soft and removal paths.** F03/F04/F05 fix ordering and scope. Generic keys
use the same conflict behavior as parking. Canonical hard/soft/context paths are
exact. Legacy unqualified parking continues to remove both scopes; this is
intentional and deterministic, not an arbitrary choice of one scope.

**Transport.** Reviewed; no change required to the transport-to-context mapping
or the ban on inferred parking. Existing tests cover motorbike, car, bicycle,
public transport, ride hailing, walking, near, distance and travel time. The
walking variant `đi bộ tới được, không quá xa` retains walking+near and remains
eligible for fallback if its residual wording is unresolved. It does not become
a relative decrease. No rule coverage was added just to absorb that residue.

**Explicit evidence.** Parking evidence filtering remains shared by both model
routes. The common prompt now explicitly prohibits inventing budget/cuisine/
distance/parking from date context and facilities from children as companions.
This is an extraction instruction, not a claim of exhaustive semantic proof for
arbitrary model-generated constraints.

**Safety versus dislike.** Negative spicy and hard peanut exclusion remain
distinct. F09 preserves exclusions across additions. Vegetarian remains a hard
rule constraint. Vegan, halal and kosher remain provider-interpreted extensible
attributes where explicitly stated; no new taxonomy was introduced.

**Food/cuisine.** Across-turn set values replace the previous list. Synthetic
interactive tests verify corrected food is used by the following request.
Japanese aliases remain canonicalized. F10 stops an incorrect rule-only
replacement interpretation. No food/cuisine attribute was promoted into a filter.

**Context lifetime.** Context deltas merge and preserve unrelated keys without
mutating input. Explicit meal-time and transport corrections replace prior
values. No automatic time-based expiration was added. Known context aliases and
positive-integer party size remain validated.

**References and feedback.** Reviewed; no change required. Existing and added
offline coverage verifies standalone rank 2 -> R002 without model invocation,
positive/similar-to enrichment, and a current-turn distance decrease without
state persistence. IDs still come from caller-provided results.

## 4. Architecture and all-path schema review

| Path | Result |
| --- | --- |
| Public PreferenceUpdate | All nine fields remain present with legacy defaults, including context_updates={}. New writes now share known constraint validation. |
| Rule parser | Emits context_updates and canonical removals; F10/F11 address concrete semantic errors. |
| Gemini / OpenAI | Reviewed; no provider-specific semantic divergence. Both use StructuredPreferenceUpdate and its shared converter. No adapter/network/retry code changed. |
| Structured converter / mock provider | context_updates survives wire entries -> public dictionary; legacy missing fields still default. F07/F08 align validation. |
| Normalization / State Manager | Revalidates mutated deltas; resolves removal scopes before conflict cleanup; merges context independently; keeps relative events out of state. |
| Interactive display / correction | context_updates is displayed and accepted in corrections. State rebuilding remains OLD STATE + HUMAN CORRECTION; next request uses the corrected state. F14 adds the missing timing projection. |
| Dataset logger / export | Reviewed; no label-selection or target-selection change required. Both carry context in their full delta serialization. |
| Benchmark evaluator | Both state.context and update.context_updates are reachable through the existing view. F16 fixes empty-map assertions; source expectations were not changed. |
| SLM contract | Message, current_state, full rule_result and previous_results remain JSON/Pydantic data, without SDK objects. Target remains PreferenceUpdate v0.2. F12 tightens result validity. |
| Shared normalization | Removed duplicated parser removal cleanup because its ordering caused F03. This was a correctness change, not a style rewrite. |

Mutable defaults use factories. State/model inputs are copied before mutation.
Provider exceptions remain bounded codes; SDK usage omissions do not invalidate
successful provider responses. Real provider semantics remain unmeasured offline.

## 5. SLM-disabled and observability verification

- LOCAL_SLM_ENABLED defaults to **false**. A guarded-import regression forbids
  SLM/heavy-runtime/provider SDK imports while exercising the disabled route.
  One unresolved request goes to the injected external mock, with slm_called=false,
  slm_confidence=null and slm_ms=0. No model lookup/loading/inference occurs.
- Sufficient rules bypass both layers. Existing tests cover confidence exactly
  at 0.80, below threshold, explicit fallback, invalid output, exception and
  enabled-but-disabled backend. The fallback executes once, without retries.
- Unknown backends safely fall back with slm_unavailable; F13 distinguishes
  factory failure from a provider invocation.
- Invalid confidence configuration (negative, >1, NaN, infinity, nonnumeric)
  raises ValueError before inference. This fail-fast configuration behavior is
  intentional; it is not silently replaced with an unsafe threshold.
- requires_llm continues to mean “unresolved after rules,” including a turn
  subsequently handled by SLM. parser_used distinguishes hybrid_slm/hybrid_llm.
  A provider_unavailable error with llm_called=false is a configuration failure,
  not a claimed network request.
- The existing raw rule timing name remains rule_parse_ms; the interactive
  latency projection calls it rule_ms. slm_ms/llm_ms/total_ms are preserved.

## 6. Training-data and secret safety

**Genuinely user-reviewed human-labeled samples: 0**, per the supplied provenance.
No manual review was performed during this audit. Tests create synthetic fixtures
in temporary directories; these are not training labels and were not added to
the project's historical dataset.

Reviewed; no change required to export eligibility: accepted/corrected only;
unreviewed/rejected are excluded. Corrected targets use the correction rather
than the original prediction. schema_version remains "0.2". Old missing
context_updates defaults to {}; old semantic labels are not reinterpreted.
No historical logs or exports were relabeled, rewritten or auto-accepted.
An accepted/corrected string is not proof of genuine human review: exploratory
historical artifacts remain unsuitable as ground truth without a real review.

Existing .gitignore rules cover .env, .env.*, logs, interactive data and benchmark
results. F15/F17 fix the two demonstrated output leaks. SDK exception messages
are not logged. UTF-8 export regressions check literal round trips for cơm tấm,
cái thứ hai, đi xe máy, đừng quá ồn and dị ứng đậu phộng using UTF-8 bytes and
ensure_ascii=False. No credentials were opened or printed during the audit.

## 7. Tests and compatibility

Command: `.venv/Scripts/python.exe -m pytest -q`.

| Stage | Total | Passed | Failed |
| --- | ---: | ---: | ---: |
| Before, reverified | 537 | 537 | 0 |
| After | 593 | 593 | 0 |

All 56 new cases are in tests/test_v02_audit.py. Existing 537 cases and their
assertions are unchanged; no PRE-v0.2 expectation needed another migration.
The suite's network guards remained enabled. Provider parity tests use fake SDK
objects/local mock transports, never real API endpoints.

Compatibility changes are deliberate: malformed known constraints or misplaced
state fields now fail validation rather than reaching state/export. Valid legacy
custom dictionary content is retained. Allergy additions are now cumulative;
explicit caller replacement or canonical removal is required to clear them.
Unqualified numeric removals use existing scopes. Real-provider wire projection
is still shared; legacy domain model container corrections now act as deltas.

## 8. Benchmark and source verification

Latest offline artifact:
[ai2_mock_v02_high_audit.json](../benchmarks/results/ai2_mock_v02_high_audit.json).
Execution used an explicitly configured empty mock, SLM disabled and sockets
blocked, without loading provider credentials.

- 105 prompts / 15 categories.
- 30 rule-only: **28.57%**, unchanged by this audit; 75 empty mock fallback calls.
- 36/54 evaluated prompts satisfy all frozen assertions; 80/98 checked fields
  match. There are 0 API errors and 0 validation errors.
- Empty mock responses do not resolve unknown semantics; these are rule/harness
  figures, not external-model or SLM quality estimates.
- Routing compared with the migration artifact: **no changed prompt routes**.
- The earlier comparable 15-case improvement from 7/15 to 8/15 is attributable
  to multiple_constraints_001: “Ramen dưới 150k, trong 2km, bắt buộc có chỗ đậu
  xe.” Explicit hard parking completes that parse legitimately. The audit also
  inspected all 30 rule-only messages. F10 was found outside this frozen sample
  set and fixed even though benchmark coverage does not change.

Source SHA-256 before and after:
`3067D0B66E9F0D16DB316A1DAB766406C115C936B78133F200E370C6B434E5C8`.
**Benchmark source changed: NO.**

## 9. Files changed

Created:

- docs/AI2_V02_HIGH_AUDIT.md
- tests/test_v02_audit.py
- benchmarks/results/ai2_mock_v02_high_audit.json

Modified for the findings above:

- src/common/schemas.py
- src/conversation/context.py
- src/conversation/normalization.py
- src/conversation/parser.py
- src/conversation/state_manager.py
- src/conversation/rule_parser.py
- src/conversation/providers/structured.py
- src/conversation/prompts.py
- src/conversation/conversation_logger.py
- src/conversation/slm/base.py
- src/conversation/slm/disabled.py
- src/conversation/interactive/session.py
- scripts/ai2_tools.py
- scripts/check_ai2_slm_dataset.py
- docs/AI2_PREFERENCE_SCHEMA_V02.md

AI1/AI3, dependencies, provider network implementations, old tests, historical
training artifacts and benchmark source samples were not modified.

## 10. Remaining risks / TODOs

- Correction/evidence checks are deliberately bounded Vietnamese rules, not a
  complete semantic verifier. Unrecognized clauses still require model
  interpretation; conditional/complex negation remains an evaluation target.
- Arbitrary extensible attributes rely on extraction instructions and subsequent
  human review. Offline tests do not prove that an external model never invents
  an unstated constraint. No real-provider quality claim is made.
- SLM confidence calibration, actual backend inference and dataset suitability
  remain future work. The scaffold is not a trained or evaluated model.
- Legacy snapshots retain permissive custom JSON for compatibility. New known
  writes are validated; this audit does not silently repair/relabel all historical
  custom fields or invent context expiration rules.
- Human training data remains unavailable. Do not train from exploratory logs
  merely because an old artifact contains an accepted/corrected status string.

## 11. Final execution confirmations

| Item | Result |
| --- | --- |
| Before | 537 passed |
| After | 593 passed, 0 failed |
| Bugs found / fixed | 18 / 18 |
| Real Gemini calls | 0 |
| Real OpenAI calls | 0 |
| Actual SLM inference calls | 0 |
| SLM training runs | 0 |
| Model downloads | 0 |
| torch / transformers installations | 0 / 0 |
| Reviewed human-labeled training samples | 0 |
| Benchmark source changed | NO |
| LOCAL_SLM_ENABLED default | false |

Synthetic fake-provider calls exercised routing only; they are not model inference.
