# AI2 OpenRouter primary/backup — local implementation handoff

Implemented in the current `<development-checkout>` checkout. No branch,
remote, commit, cleanup, training, adapter or frozen-data/report changes. No paid
API calls. This is an implementation/regression handoff, not a readiness claim.

## Architecture and compatibility

The existing `process_user_request` → `parse_user_input_detailed` → `update_state`
path remains authoritative. No parallel pipeline, alternate shared schemas or
backend/frontend changes. The backend adapter still consumes the same state,
parser_used and clarification_required fields. Public AI2 function signatures and
PreferenceUpdate/UserPreferenceState/StructuredPreferenceUpdate are unchanged.

New explicit mode `LLM_PROVIDER=openrouter_chain` uses Rule first; confidently
parsed requests/no-op acknowledgements bypass inference. Remaining turns call
Gemini `google/gemini-3.5-flash-lite` via OpenRouter. Only a provider/validation
failure invokes `openai/gpt-5.4-mini`, once, with the same original state, message,
Rule context and caller results. Rejected primary output is not backup context.
There is no majority vote, unconditional double dispatch or hidden model substitution.

Factory uses existing OpenRouterProvider with verified profiles: Gemini sends
reasoning.enabled=true; GPT-5.4 sends reasoning.effort=none and **omits temperature**.
Both use strict JSON Schema, require_parameters=true, allow_fallbacks=false,
max_tokens=512 by default, zero client retries and configured timeout=30s/model.
Returned model identity is verified. Truncation/refusal, invalid JSON/schema,
timeouts, errors and detectable unsafe deltas fail acceptance. Billing usage is
retained when available even for invalid responses.

The chain can therefore take up to two provider timeouts; account-wide quotas,
concurrency, spending caps and deployment settings need operational verification.
Backup shares the same OpenRouter account and does not solve an account-wide
credit/rate-limit failure. No benchmark pacing/sleep was added to request handling.

## Safety and state semantics

Each candidate passes existing grounding, schema validation, deterministic
reference resolution, Rule/form merge, normalization, evidence checks and State
Manager preview before acceptance. Additional bounded checks reject unsupported
allergen substitutions/removals, ungrounded food/cuisine/coordinates/context,
negated constraints, invented IDs/ranks/sentiment and contradictory relative events.
An authoritative form still takes precedence over model values.

Alias additions are exact mappings for walnut/quả óc chó and pistachio/hạt dẻ cười,
using existing extensible string constraints. No substitution with peanut/cashew,
schema enum expansion or gold label change. Unsupported/uncertain allergens remain
clarification cases; allergy metadata coverage in retrieval is a separate concern.

Bounded vegetarian detection now retains full “bún riêu chay”/“bánh mì chay” and
vegetarian=true, including when a provider returns only the base dish phrase.
Existing negation/conditional/name exclusions still apply. Transport “chuyển từ
đi bộ sang xe máy” can override the old mode; negated kilometres cannot supply a
minute-bound distance. Relative updates remain turn events, with no numeric policy.
Known explicit negative reference feedback cannot silently disappear in acceptance.

Allergy retraction is target scoped: explicit single-target commands (including
CN05's named historical milk allergy + “đã hết ... bỏ ràng buộc đó”) remove milk
while retaining peanut and every unrelated hard constraint. The parser constructs
a complete validated hard-constraint replacement through the existing set_values
contract; State Manager semantics and removal-wins ordering are unchanged. This
records the user's requested preference change, not verification of a medical claim.
Bare-pronoun, unnamed, conditional, negated or competing-target retractions preserve
state and request clarification; coordinated multi-target removal awaits policy.
Historical allergy statements without a current confirmation/removal also clarify.
A combined retraction plus relative event clarifies atomically, because replacing
the full hard container would suppress the event under existing absolute-wins
normalization. It does not silently remove the allergen while losing that event.

If both providers fail, or final safety checks cannot establish an acceptable
update, the delta is empty, clarification_required/state_preserved are true and
the service returns a deep copy of the original state. Even a partially parsed
Rule/form change is not committed on this failed transaction. The caller's input
objects are never mutated. Pure Rule/form success retains normal State Manager behavior.

Local Qwen stays available in legacy opt-in modes; V3 remains the adapter default
and V4 is opt-in. The cloud chain skips local-first inference even if local is
enabled. It does not automatically apply a local guess after both cloud providers
fail; explicit local operation remains a caller choice.

## Configuration — not activated by this change

No `.env` or process environment was modified. Existing `none`, `mock`, `gemini`,
`openai` and single `openrouter` modes retain their configuration and behavior.
Legacy OpenRouter model/default parameters are preserved for existing consumers.

To select the agreed chain later, set these server environment values:

```dotenv
LLM_PROVIDER=openrouter_chain
OPENROUTER_ENABLED=true
OPENROUTER_API_KEY=<server environment only>
OPENROUTER_PRIMARY_MODEL=google/gemini-3.5-flash-lite
OPENROUTER_BACKUP_MODEL=openai/gpt-5.4-mini
OPENROUTER_CHAIN_MAX_TOKENS=512
OPENROUTER_TIMEOUT=30
LOCAL_SLM_ENABLED=false
```

The explicit existing .env loader recognizes the added keys and never overrides
shell variables. Config construction itself performs no network/client/model I/O.
Only the agreed two model profiles are permitted in chain mode. No API key appears
in config repr, diagnostics, exceptions or frontend data. Conversation logging
continues to use existing credential redaction.

## Diagnostics

Existing metadata fields remain; additive internal fields are provider_models,
provider_errors (bounded codes, no exception text), fallback_used and
state_preserved. provider_attempts/usage aggregate called providers. cost_usd is
the summed actual returned cost only when every attempted provider has known cost;
otherwise it stays null. llm_ms includes the provider/acceptance path, total_ms
includes the complete turn. Logging failure cannot invalidate an accepted update.

## Local verification commands — offline

```powershell
.\.venv-fullstack\Scripts\python.exe -m pytest -q -p scripts.sealed_benchmark_guard tests/test_ai2_production_pipeline.py tests/test_ai2_safety_patch.py tests/test_conversation.py tests/test_openrouter_provider.py tests/test_slm_partial_repair.py tests/backend/test_conversation_adapter.py
.\.venv-fullstack\Scripts\python.exe -m pytest -q -p scripts.sealed_benchmark_guard
.\.venv-fullstack\Scripts\python.exe examples/integration_demo.py
```

Tests use synthetic providers/transport with offline socket guards; no key, cloud,
GPU model load or payment is needed. The integration demo explicitly pins offline
Rule behavior and synthetic AI1/AI3; it is a contract check, not retrieval quality.

Exact expanded targeted command used for the 524-test result:

```powershell
.\.venv-fullstack\Scripts\python.exe -m pytest -q -p scripts.sealed_benchmark_guard tests/test_ai2_production_pipeline.py tests/test_ai2_safety_patch.py tests/test_ai2_adapter_integration.py tests/test_ai2_freeze_findings.py tests/test_ai2_v4_runtime_fixes.py tests/test_conversation.py tests/test_openrouter_provider.py tests/test_providers.py tests/test_slm_partial_repair.py tests/test_common_contracts.py tests/test_schema_v02.py tests/test_module_imports.py tests/backend/test_conversation_adapter.py tests/backend/test_search_clarification.py tests/backend/test_ai2_updated_ai1_integration.py
```

Initial targeted regression run: 786 passed before the final extra safety cases.
Final targeted run: **524 passed in 16.36s**, including **50 new production tests**;
no xfails in that run. The offline integration demo passed. `git diff --check`
passed (line-ending notices only). SHA256 audit of 790 incoming protected files
found only the nine intended existing AI2 source edits and no unexpected changes.
The optional full-repository sweep was interrupted during expensive historical
labeling-workflow tests; it did not complete and is **not** reported as passing.
It reported no failures before interruption. The final targeted run covers the
latest source; the broader sweep started before the last chain-only checks.
Results and integrity checks are recorded in
`logs/ai2-production-pipeline-20261015/` (`final-delivery-targeted-tests.xml`,
`integrity-after.json`, `runtime-change.patch` against incoming work).
New test cases cover FD01, FD02, AL01, AL05, CN01, CN05, TR05, provider failover,
complete failure rollback, no-op, references/feedback, relative events, forms,
verified transport parameters and the current backend adapter contract.

## Changed files and remaining validation

- `src/conversation/config.py`, `environment.py`, `providers/openrouter_provider.py`: explicit chain factory/config and verified wire profiles.
- `src/conversation/parser.py`, new `safety.py`, `evidence.py`: bounded acceptance/fallback, scoped removal, rollback signaling.
- `src/conversation/service.py`, `models.py`: preserve the failed transaction's original state; additive diagnostics.
- `src/conversation/normalization.py`, `rule_parser.py`: exact aliases/dietary phrases; no shared schema or State Manager edits.
- `tests/test_ai2_production_pipeline.py`, `tests/conftest.py`: deterministic regressions and environment isolation for added keys.
- This handoff and `docs/ai2_conversation.md`.

Bounded checks cannot prove arbitrary multilingual semantic correctness. Unknown
constraints/context and ambiguous references may require clarification. End-to-end
hard-constraint consumption, allergen metadata completeness and restaurant safety
remain AI1/AI3/backend integration validation; those modules were not changed.
The previous full47 cloud outputs are historical evidence for extraction, not a
live test of these new guards or operational failover. Validate with an approved
fresh evaluation before freeze; distinguish objective candidates/policy-review
and independently adjudicated gold. Do not declare production readiness from
JSON compliance or mocks. No production routing was silently activated.
