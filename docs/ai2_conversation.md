# AI 2 — Conversation + Preference State

## Ownership and current status

The current OpenRouter web architecture is [LLM-first](AI2_LLM_FIRST.md): one
Gemini interpretation supplies intent, preferences and conversational reply;
GPT and optional local V4 follow only on failure. The earlier rules-first
descriptions below remain relevant to explicit compatibility/offline modes.

Own `src/conversation/`, `data/ai2_interactive/`, `notebooks/ai2/`, this document,
AI 2 tests and the existing interactive/benchmark tooling. The implemented
Preference Schema v0.2 and conversation semantics are the source of truth.
The High audit records an earlier 593-test milestone. Current setup and artifact
requirements are documented in [setup](setup.md) and [artifact audit](artifact_audit.md).

## Architecture

The agreed OpenRouter chain is selected explicitly with `LLM_PROVIDER=openrouter_chain`
and `OPENROUTER_ENABLED=true`: Rule → Gemini 3.5 Flash Lite → GPT-5.4 mini only on
failure/rejected evidence → existing normalization/guards/State Manager. See
[production pipeline handoff](AI2_PRODUCTION_PIPELINE_HANDOFF.md) for configuration,
rollback/clarification semantics and offline verification. Legacy provider modes
and local V3/V4 remain available; selecting the chain skips local-first inference.
The following diagram documents those legacy modes.

```text
Conservative typo preprocessing + optional English-to-Vietnamese translation
  ->
Rule + deterministic reference resolution
  -> optional Local SLM [Qwen3-1.7B + LoRA V3; opt-in]
  -> Gemini/OpenAI fallback for unresolved input
  -> normalization
  -> State Manager
```

`LOCAL_SLM_ENABLED=false`, default backend `qwen_lora`, minimum confidence 0.80.
Fully understood rule inputs bypass inference. Disabled routing avoids loading
local models. Both external provider adapters retain their existing fallback.

## Optional local Qwen LoRA inference

### V4 integration, opt-in adapter selection and external fallback preparation

Defaults retain V3 and `LOCAL_SLM_ENABLED=false`. Set
`LOCAL_SLM_ADAPTER_VERSION=v4` to use the delivered local directory
`models/ai2/best_adapter_v4_experimental`; `LOCAL_SLM_ADAPTER_PATH` takes priority
if explicitly set. The anticipated `ai2-qwen3-1.7b-lora-v4` release path does not
exist in this checkout. Adapter paths resolve relative to the checkout, with
absolute paths supported; nothing is renamed, merged or overwritten.

`LOCAL_SLM_LOCAL_FILES_ONLY=true` now prevents base downloads/metadata refresh by
default. Missing cache is a controlled local failure, not permission to download.
V4's recorded base revision is respected for a model ID. Explicit local base
directories remain supported. NF4/double quantization/float16 and the existing
single CPU retry after CUDA load OOM remain unchanged.

Rules now recognize exact sesame/milk aliases and bounded explicit allergy lists.
Model evidence checks protect known targets and reject unrelated removal of prior
allergies. Mentioning retained confirmed allergies does not require them to be
repeated in the current delta. Reference mentions come from actual deterministic
selectors where available; plain cheaper/closer feedback supplies no sentiment
or similarity by itself. Pure deictic turns cannot create attributes. Explicit
15-minute evidence is checked without inventing travel-distance conversion.
State Manager and public shared schemas remain unchanged.

OpenRouter is prepared behind both `LLM_PROVIDER=openrouter` and
`OPENROUTER_ENABLED=true`; the flag defaults false. Gemini's configuration and
provider policy are preserved. See [provider audit](AI2_OPENROUTER_AUDIT.md),
[environment reference](AI2_RUNTIME_ENV.example),
[baseline and patch proposal](AI2_V4_INTEGRATION_BASELINE.md), and
[cleanup plan](REPOSITORY_CLEANUP_PLAN.md). CLI/backend explicit .env loaders
accept the new local/OpenRouter keys; ConversationConfig does not auto-load .env.

New runtime reports are in `logs/v4-integration/`, never replacements for old
benchmark outputs. The authored probes are screened against train/validation
and are diagnostic regressions, not independently reviewed benchmark gold.

Install optional dependencies with `python -m pip install -e ".[slm]"`; this extra
already includes bitsandbytes. The diagnosed Windows runtime uses 0.50.2.
`src/conversation/slm/qwen_lora.py` lazily loads the base and attaches the local
PEFT adapter in evaluation mode. The router caches the provider, and the provider
serializes loading/generation and reuses its tokenizer/model. No training,
adapter merging, model writes or import-time model/SDK loading occurs.
Base loading only permits downloads if `LOCAL_SLM_LOCAL_FILES_ONLY=false` is explicitly set;
the adapter and its tokenizer are always loaded locally. A local base directory
can be supplied instead of the model ID. Relative artifact paths resolve against the checkout.

Configuration (also in `.env.example`):

```text
LOCAL_SLM_ENABLED=false
LOCAL_SLM_BACKEND=qwen_lora
LOCAL_SLM_BASE_MODEL=Qwen/Qwen3-1.7B
LOCAL_SLM_ADAPTER_PATH=models/ai2/ai2-qwen3-1.7b-lora-targeted-v3
LOCAL_SLM_MAX_NEW_TOKENS=512
LOCAL_SLM_MIN_CONFIDENCE=0.80
```

`disabled` remains a supported backend. Legacy `LOCAL_SLM_MODEL` remains readable;
Qwen uses the explicit base/adapter settings. Generation is greedy, one beam,
with a validated limit of 1–4096 new tokens. The runtime uses Torch,
Transformers, PEFT, Accelerate and bitsandbytes. CUDA must be available for this
GPU loading path. The base uses 4-bit NF4, double quantization and float16 compute
with an explicit single-GPU device map. The loader verifies quantized weights
are materialized before attaching the adapter, then rejects meta parameters
(including LoRA), unexpected parameter placement and meta buffers before caching.
Adapter loading uses `low_cpu_mem_usage=False`, explicit placement and no adapter
dtype promotion. The successful model/tokenizer pair is reused across requests.

Only a CUDA out-of-memory error during base/adapter loading triggers one fresh
full-CPU NF4 attempt using the same quantization settings. This slower fallback
requires bitsandbytes CPU support and sufficient system RAM; it uses no mixed
CPU/GPU or disk offload. Both stages must pass the same materialization checks.
If that attempt fails, the existing parser fallback remains in effect. Generation
failures retain their existing fallback and do not trigger model reloads.
See the [Qwen model card](https://huggingface.co/Qwen/Qwen3-1.7B) and
[PEFT loading API](https://huggingface.co/docs/peft/package_reference/peft_model).

The training contract was checked against `train_sft.jsonl` inside the local
`ai2_sft_v1.zip`; the final chat wrapper was confirmed by the model owner:

1. Exact instruction: `Trích xuất PreferenceUpdate v0.2 cho AI2 Food Recommender. Chỉ trả về một JSON object hợp lệ, không giải thích.`
2. Append a newline and UTF-8 JSON with `sort_keys=True`, `separators=(",", ":")`.
   Input keys are `message`, `current_state`, `rule_result`, `previous_results`;
   serialize the complete SLMInput, including the complete RuleParseResult.
3. Wrap the whole input as one user message using `apply_chat_template` with
   `tokenize=False`, `add_generation_prompt=True`, `enable_thinking=False`.
4. Training target was canonical nine-field PreferenceUpdate JSON as plain
   assistant continuation followed by EOS. Inference decodes only new tokens.

Strict parsing requires one complete JSON object with all nine fields, rejects
duplicate keys/non-finite values, and validates PreferenceUpdate. No markdown
stripping, guessed repairs or duplicated normalization is performed. Load,
generation and parse failures return fallback with sanitized error codes.
For explicit local diagnostics, the provider exposes `load_summary`,
`last_load_error` and `last_gpu_load_error` (exception tracebacks stored as text,
outside ordinary routing metadata/logs).
The existing parser still resolves IDs, preserves rule/form precedence, calls
`normalize_update()`, validates state application and falls back externally.

The provider's fixed confidence 0.80 is **structural acceptance only**, not a
measured semantic probability or accuracy claim. A threshold above 0.80 forces
fallback. Semantic quality still needs explicit evaluation; valid JSON is not
proof of correct understanding.

From the repository root, explicitly run one real diagnostic:

```powershell
.\.venv\Scripts\python.exe scripts/local_slm_smoke_test.py --run --case food
```

Omit `--case food` to run all authored cases. This script directly diagnoses the
SLM on every selected case, then replays its result through the existing pipeline
without a second generation. Rules may bypass that replay. It prints input,
prior state, prior results, raw response, effective normalized update and final
state, plus failure/routing metadata. External inference and logging are disabled.
It never runs automatically in pytest/CI. Tests mock all runtime loaders.
`SLM LOAD PLACEMENT` reports `cuda_nf4`, 4-bit status, counts of parameter tensors
per device, LoRA placement and zero meta parameters on a successful GPU load.
Accelerate CPU/disk offload and meta-parameter warnings are not expected on that
path. A CUDA OOM emits an explicit CPU retry warning and, if successful, reports
`cpu_nf4_fallback`. `SLM GPU LOAD ERROR` and `SLM LOAD ERROR` expose the underlying
tracebacks when applicable. Successful loading does not guarantee valid generated
JSON or enough VRAM for every prompt/KV cache; inspect `RAW SLM UPDATE` and
`SLM STATUS` separately.

Canonicalization and residual-routing policy, including canonical known context values
versus open food names, is documented in
[Preference Schema v0.2](AI2_PREFERENCE_SCHEMA_V02.md#canonicalization-and-routing-policy).
Use `python scripts/audit_ai2_routing.py` for repeatable offline diagnostics.

## Qwen V4 input preparation

This is preparation only: no V4 training, weights, adapter changes, benchmark
relabelling or real translation/Gemini calls. The Rule -> opt-in Qwen -> external
fallback order and default 0.80 structural confidence threshold are retained.
`common.schemas.PreferenceUpdate` and `UserPreferenceState` keep their fields,
types and interface version. Internal `ParserMetadata` now records original and
parsed messages, typo edits and translation attempt/success/error status. Logging
keeps the original `message` and redacts the additional text with existing rules.

Exact canonical mappings added:

| Scope | Alias | Canonical value |
| --- | --- | --- |
| semantic | không gian yên tĩnh, quiet ambience, quiet atmosphere | quiet |
| negative | không thích cay, không thích đồ cay, không ăn cay, không muốn ăn cay, đừng cay, don't like spicy food, i don't like spicy food | spicy |
| negative | đậu phộng, lạc, peanuts | peanut |
| allergens_excluded | peanuts | peanut |
| allergens_excluded | hải sản, seafood | seafood (broad scope retained) |
| transport_mode | on foot, by motorbike, by car, by bicycle | walking, motorbike, car, bicycle respectively |
| meal_time | late night | late_night |
| companions | solo | alone |

Existing `món Nhật -> japanese`, `yên tĩnh -> quiet`, Vietnamese context and
allergen aliases remain. Food names (`phở`, `bún bò`, `bánh xèo`), names/IDs,
unknown cuisines/preferences/constraint values remain open and unchanged.
Known transport/occasion/meal-time fields retain their canonical vocabulary;
unapproved labels are rejected. Custom context keys and companion labels remain
open. A negative peanut preference never creates an allergy exclusion. New narrow rules understand
`ưu tiên/thích có điều hòa` as soft, `bắt buộc/phải có điều hòa` as hard, and
`không thích đậu phộng/lạc` as negative.

Configuration is read per request from environment variables (no automatic
`.env` loading):

```text
AI2_INPUT_NORMALIZATION_ENABLED=true
AI2_TRANSLATION_ENABLED=false
LOCAL_SLM_ENABLED=false
```

Set `AI2_INPUT_NORMALIZATION_ENABLED=false` to disable typo preprocessing.
Corrections are exact and contextual, including sentence-initial capitalization:
`Cho mik -> Cho mình`, `cho/giúp mik -> cho/giúp mình`,
`mình/tôi/... mún ăn/tìm/... -> muốn`, and `quán/không gian/chỗ yên tĩn -> yên tĩnh`.
Quotes, supplied dish/restaurant names and recognizable proper names are protected.
No fuzzy spelling correction, geographic guessing or dataset lookup is performed.
Preprocessing changes only the parsing message; form, current_state and
previous_results stay caller-owned and are not rewritten.

To enable translation, set `AI2_TRANSLATION_ENABLED=true` and inject an object
implementing `conversation.preprocessing.Translator`:

```python
from conversation.config import ConversationConfig
from conversation.service import process_user_request

# my_translator.translate(text, *, source_language="en", target_language="vi")
# must return a string and preserve AI2KEEP0X, AI2KEEP1X, ... exactly once,
# in order. It receives text only, not form/state/results or credentials.
result = process_user_request(request, config=ConversationConfig.from_env(),
                              translator=my_translator)
```

The same keyword works with `parse_user_input` and `parse_user_input_detailed`.
The flag defaults to false even when a translator is supplied. A flag without
an injected translator reports `translator_unavailable`; no SDK/client is
created. This change supplies no Google adapter or dependency. A future Google
Cloud Translation implementation must use the official SDK as an optional
extra/explicit opt-in; unofficial endpoints and scraping are unsupported.

English detection uses grammatical request/first-person frames and at least three
tokens (including protected entities), with no remaining Vietnamese markers or
accented words. There is no English dictionary coverage threshold: `vegan`,
`cheap`, `halal`, and unfamiliar descriptors such as `pescatarian` may translate.
`Find bun cha under 100k` preserves `bun cha` and `100k` as separate literals.
Dish/location slots are protected only when they do not conceal uncertain
Vietnamese text. `Find quán yên tĩnh under 100k` therefore skips translation;
the mixed phrase cannot be classified as a name merely by masking it.
Explicit quotes, caller-supplied names and known dish names remain protected.
The finite capitalized-token table only helps distinguish grammar/known cues
from possible proper names; it does not determine English vocabulary membership.
Single dish names and uncertain mixed language skip translation. This heuristic
is not a calibrated probability or a complete language classifier. Some clear
English requests outside these frames and unknown names may still be skipped
or over-protected. Remaining ordinary descriptors are translated, not masked
merely because they are absent from a word list.

Empty/invalid/unchanged responses, missing/reordered/repeated tokens, added
numbers/known currencies/units or recognizable dish names, and losses/additions
of known bilingual cues are rejected. Checks compare allergy target identity
and polarity within each simple clause; supported targets include peanut,
shellfish, seafood, milk, egg, soy, wheat, sesame and fish. Shellfish is matched
to `động vật có vỏ`/`hải sản có vỏ`, not the broader `hải sản`.
Unknown targets or unverified conditional/uncertain allergy syntax use the
original parsing message without calling the translator (`translation_unverifiable`
when the English frame passes). Meal/facility checks bind breakfast/lunch/dinner,
tonight, AC and parking to their clause's negation/obligation/preference cues.
Conflicting modalities in one recognized clause fail closed rather than guessing
their scope. Existing spicy/quiet, budget-bound, cheaper and ordinal checks remain.
Provider exceptions report `translation_failed`; failed checks report
`translation_rejected`, with success false. Parsing then uses the original
message after any enabled safe typo edits. Exception text is never logged.

Deterministic model evidence checks reject observable single-bound VND/km
contradictions (including meters to km), explicit peanut-dislike or negated-allergy
exclusions, and AC wishes promoted to hard. Existing rule/form precedence remains.
Constraint validation rejects float/string/bool budgets and unknown envelope fields.
Checks cannot prove arbitrary translation/parsing semantics, detect every new
field hallucination, or guarantee unknown named-entity recognition. Unrecognized
modifiers/conditions remain available to existing inference fallback; this is
not a measured quality improvement or a complete semantic validator.

Examples below use mock translations. Only nonempty update fields are shown;
all other fields retain the existing empty defaults.

| Original | Parsing message | PreferenceUpdate |
| --- | --- | --- |
| cho mik quán yên tĩn xíu | cho mình quán yên tĩnh xíu | add_semantic_preferences=[quiet] |
| Find a quiet restaurant under 100k | tìm quán yên tĩnh dưới 100k | add_semantic_preferences=[quiet], add_hard_constraints={budget_max:100000} |
| I'm allergic to peanuts | dị ứng đậu phộng | add_hard_constraints={allergens_excluded:[peanut]} |
| I'd prefer air conditioning | ưu tiên có điều hòa | add_soft_preferences={air_conditioning:true} |
| I don't like spicy food | không thích cay | add_negative_preferences=[spicy] |
| Find something like the second restaurant but cheaper | tìm quán giống quán thứ hai nhưng rẻ hơn | references resolve caller rank=2 IDs; relative_updates={budget:decrease} |

The last example uses a mocked parser for similarity intent. Relative events
stay in the update and never change a persisted budget or enter state context.

`tests/test_ai2_preparation.py` covers these examples, typo flags, language gating,
translation failures/cue mismatches, entities/units, logging, form precedence,
Rule/Qwen/external routing, canonical removals, and AI2 -> fake AI1 -> fake AI3.
`tests/test_ai2_preparation_review.py` adds independent semantic counterexamples,
open English descriptors, capitalized typos and mixed-language masking regressions.
Contract tests cover canonical known context and open custom values with the
unchanged public fields. Partial-repair tests retain the original invalid
`occasion="chat"` fixture: valid SLM preferences survive, only the rejected
context path is repaired, and accepted Rule/Form/SLM values stay protected.
Sealed benchmark data/answers and
historical logs/labels/training exports are untouched. Run regressions with:

```powershell
.\.venv-fullstack\Scripts\python.exe -m pytest -q -p scripts.sealed_benchmark_guard
.\.venv-fullstack\Scripts\python.exe examples/integration_demo.py
```

Reviewed preparation snapshot before the final stability pass on branch
`ai2/qwen-v4-preparation` (from `fullstack`):

- Full offline regression: **1327 passed, 35 skipped, 0 failed**, Python 3.11.7,
  with `-p scripts.sealed_benchmark_guard --basetemp=.pytest_cache/ai2-review-full`.
  Skips include sealed-benchmark readers and tests requiring optional SDK/database
  setup. A system-Python 3.14 attempt stopped at collection because backend/database
  dependencies were missing; the existing `.venv-fullstack` supplied them.
- `examples/integration_demo.py`: passed. `git diff --check`: passed.
- The new preparation file supplies 68 offline cases, including fake AI1/AI3
  integration. The independent review file supplies 52 cases; shared tests cover
  canonical context, open custom values and unchanged schema fields.
- Targeted AI2, partial repair, contract and integration run: **687 passed**.
  The interrupted mixed-language case was reproduced with `-vv --tb=long`:
  9 parameterized cases passed and `Find quán yên tĩnh under 100k` failed because
  the entity preprocessor masked the Vietnamese phrase as a name. The fix keeps
  that phrase visible to the detector; the original assertion is unchanged.
- `test_slm_partial_repair.py` is restored to its HEAD/fullstack version, with no
  remaining diff. `occasion="chat"` is rejected and repaired while valid SLM
  preferences, accepted context, Rule/Form values and relative events survive.
- No commits/pushes, training, API calls, model downloads or artifact/dataset
  modifications were performed. Pre-existing `.env.example` deletion and three
  untracked benchmark scripts belong to the caller's working tree and were preserved.

Review before/after (translations supplied by mocks):

| Case | Before review | After review |
| --- | --- | --- |
| Find quán yên tĩnh under 100k | Vietnamese phrase hidden as a name; translator called | No translation attempt; original message retained |
| I'm allergic to shellfish -> dị ứng sữa | Wrong allergen accepted | translation_rejected; original English passed to parsing |
| I'm allergic to milk -> dị ứng trứng | Wrong allergen accepted | translation_rejected; original English passed to parsing |
| I want dinner -> Tôi muốn ăn trưa | Changed meal accepted | translation_rejected; original English passed to parsing |
| Find a vegan/cheap restaurant; I want halal food | Word-list coverage gate skipped these requests | English frames permit their open descriptors |
| Find bun cha under 100k | Skipped translation | bun cha and 100k protected/restored verbatim |
| Cho mik quán yên tĩn xíu | Initial Cho prevented mik correction | Cho mình quán yên tĩnh xíu; semantic quiet |
| occasion=chat; transport_mode=spaceship; meal_time=unknown_time | Unapproved known labels accepted | Canonical vocabulary validation rejects them |

These are deterministic structural regressions, not semantic accuracy metrics.
Unknown allergy targets/conditions and ambiguous modality scopes fall back to
untranslated input; arbitrary translation semantics, all modifiers and every
unknown named entity cannot be verified by these checks. No Google adapter is
implemented, and translation remains disabled unless explicitly configured and
an implementation is injected.

Files changed before the final stability pass (18; exclude caller's pre-existing changes):

```text
src/conversation/config.py
src/conversation/context.py
src/conversation/evidence.py                  (new)
src/conversation/models.py
src/conversation/normalization.py
src/conversation/parser.py
src/conversation/preprocessing.py             (new)
src/conversation/rule_parser.py
src/conversation/service.py
src/conversation/state_manager.py
tests/conftest.py
tests/test_ai2_preparation.py                 (new)
tests/test_ai2_preparation_review.py          (new)
tests/test_common_contracts.py
tests/test_schema_v02.py
docs/AI2_PREFERENCE_SCHEMA_V02.md
docs/ai2_conversation.md
docs/integration_contract.md
```

## Final stability pass before V4

The final pass keeps the two earlier reviews and the existing schema, provider
order and 0.80 threshold. It makes these bounded deterministic changes:

- Two explicit allergy constructions preserve peanut/seafood exclusions, including
  `Tránh đậu phộng vì dị ứng` and `Bị dị ứng hải sản`. Multiple clear exclusions
  accumulate. Seafood is never narrowed to shellfish. Simple negation remains
  protected; dislike/nonconsumption does not become allergy. A bounded prefix
  check leaves simple conditional/uncertain allergy clauses unresolved.
- NLP merge protects known positive hard constraints against model removals.
  Existing allergy state cannot be cleared by an unrequested model removal on
  an unrelated turn. Empty/soft-only interpretations of a positive allergy cue
  fall back, preserve unresolved/original text and set service clarification flags.
  Soft allergen fields are rejected before normalization, preventing a second
  target from silently disappearing beside an already-known hard exclusion.
- Explicit meter bounds become km (`500m -> 0.5km`). Monetary prefixes are not
  treated as distance. Model `max_distance_m` and reuse of unrelated numeric
  dimensions are rejected; explicit form values keep priority.
- Ordinal references now accept `số 2` alongside `thứ hai`. Duplicate mentions
  of the same restaurant/menu IDs merge into one reference, without inventing IDs.
- AC rule evidence keeps its hard/soft category while residual companion text
  reaches Qwen in the full message and RuleParseResult. No elderly context enum
  or inferred wheelchair/transport/parking requirement is introduced.
- Distance permission `(đi) xa hơn cũng được` stays unresolved, rather than
  becoming an increase request. Relative budget feedback never invents an
  absolute budget: model budget fields on `rẻ hơn`/`cheaper` without a monetary
  amount are rejected unless provided by an explicit form. No relative event
  changes persistent numeric state.

`tests/test_ai2_stability.py` contains independent authored regressions, including
Rule/Qwen/external/partial-repair routes, missing references, named entities,
distance/form precedence, AC with older companions, and fake AI1/AI3 integration.
Three old unit fixture expectations projected in `test_conversation.py` and one
routing expectation in `test_providers.py` are explicitly updated for the new
permission policy. The source `tests/data/conversation_cases.json` is unchanged;
no benchmark labels or training records are modified. Adapter tests keep their
mock SDK call assertions by appending unparsed ambience to an input that is now
fully rule-parsed; they also assert the newly understood seafood exclusion.

Final validation on Python 3.11.7:

- Targeted AI2, contract, partial repair and fake integration tests: **914 passed**.
- Full suite with `scripts.sealed_benchmark_guard`: **1383 passed, 35 skipped,
  0 failed**, using `--basetemp=.pytest_cache/ai2-stability-freeze-full`.
  The existing skips protect sealed benchmark readers and optional SDK/database
  setups. This does not measure real Qwen accuracy or allergen filtering quality.
- The new stability file contributes **57 authored offline cases**.
- Integration demo and `git diff --check`: passed. Protected-path diff against
  `fullstack` is empty for schemas, AI1/AI3, frontend/database, SLM runtime/adapter,
  weights, data/benchmark files and dependencies.

No remaining failures or severe deterministic regressions are known in the
covered scope. Recommend freezing this AI2 logic after review for the next dataset
and V4 work; keep the semantic candidates and downstream readiness limitations
below explicit. No commit, push, merge, training, GPU benchmark or live API call
was performed.

Examples after the stability pass (only nonempty changes are shown):

| Input | Outcome |
| --- | --- |
| Tránh đậu phộng vì dị ứng | hard allergens_excluded=[peanut] |
| Bị dị ứng hải sản | hard allergens_excluded=[seafood], broad scope retained |
| Không thích đậu phộng | negative peanut; no allergy exclusion |
| Không ăn hải sản | no inferred allergy; residual intent reaches inference |
| có thể bị dị ứng đậu phộng | unresolved allergy span; empty/soft output requires clarification |
| trong vòng 500m | hard max_distance_km=0.5 |
| ngân sách thì dưới 2m | no guessed distance or amount; unknown abbreviation remains available |
| quán số 2 rẻ hơn | caller IDs resolve; budget decrease event; no invented absolute budget |
| đi xa hơn cũng được | no automatic distance increase; permission stays unresolved |
| Bắt buộc có máy lạnh, đi với người lớn tuổi | hard AC retained; full companion intent reaches Qwen |

Files touched in this pass:
`src/conversation/{rule_parser,parser,evidence,normalization,reference_resolver,preprocessing}.py`,
`tests/{test_ai2_stability,test_conversation,test_ai2_optimization,test_extensible_constraints,test_providers}.py`,
and `docs/{ai2_conversation,AI2_PREFERENCE_SCHEMA_V02,integration_contract}.md`.
State Manager, schemas, Qwen adapter/runtime and all downstream modules/artifacts
are unchanged. The preprocessing/translation flags keep their defaults (typo
normalization enabled, translation disabled); the only translation edit
additionally protects the literal meter unit.

### V4 training candidates

These are authored review topics, not exported training examples or benchmark data:

- Unknown allergens, conditional/uncertain allergy syntax, mixed negated/positive
  scopes and retraction of a prior allergy. Known cues without usable exclusions
  request clarification; deterministic checks cannot verify every model target.
- Unknown abbreviations/typos and named entities. Preserve uncertain words rather
  than guessing food, budget, geography or a new constraint.
- Similarity and sentiment around references, pronouns, conflicting selectors,
  corrections and permission versus requested distance changes in compound turns.
- Older companions and ambience, especially separate mandatory AC from remaining
  wishes. Use the current open schema instead of inventing downstream enums or
  inferring disability/facilities from age.

Freezing AI2 logic is separate from deploying allergy-safe recommendations.
Callers must honor service partial/clarification flags; the public update-only
parser cannot carry those flags. AI1's existing hard filter currently raises
NotImplementedError for unsupported allergy/AC/parking fields, so real constraint
coverage still requires owner work. Fake integration verifies interfaces/IDs only.
No semantic accuracy percentage or universal validator guarantee is claimed.

## Public interfaces and semantics

`from conversation import parse_user_input, update_state, process_user_request`.
Schemas already live in `common.schemas`; no migration was needed. UserRequest
supports form, optional message/current_state and previous_results.
PreferenceUpdate includes context_updates, canonical removals and relative_updates.
Context merges independently. Relative updates are turn-level events, never
persistent state or invented numeric changes. Forms, removal precedence, identity
validation, reference resolution and normalization retain existing behavior.

Interactive review/correction and reviewed-data export remain available through
`scripts/interactive_ai2.py` and the existing tools. An accepted/corrected status
in exploratory artifacts does not prove real human review; do not relabel or train
from historical logs automatically. Versioned export uses Preference Schema 0.2.

## Offline use and tests

```sh
python -m pytest -q -p scripts.sealed_benchmark_guard
python -m conversation.demo
python examples/integration_demo.py
```

Tests retain socket guards and fake SDK/provider transports. The integration demo
uses explicit inference-disabled configuration and real rules/state transitions.
AI 2 must not retrieve or rank restaurants.

## Detailed references

- [Safe SLM data labeling and human review](AI2_SLM_DATA_PIPELINE.md): implemented
  as optional local tooling; candidate labels require explicit review before export.
  These labeling tools do not train, download models or invoke local inference.

- [Preference Schema v0.2](AI2_PREFERENCE_SCHEMA_V02.md)
- [High audit and 593-test baseline](AI2_V02_HIGH_AUDIT.md)
- [Migration history](AI2_V02_MIGRATION_REPORT.md)
- [Original operational instructions retained in README](../README.md#ai-2-operational-reference)
- [Shared integration contract](integration_contract.md)
