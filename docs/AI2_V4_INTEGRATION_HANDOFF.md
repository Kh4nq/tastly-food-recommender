# AI2 V4 integration handoff — 2026-10-14

## Delivered scope

No training, data expansion, paid API, payment, commit/push or cleanup was performed.
Incoming labeling/runtime edits and `.env.example` deletion are retained. A safe
new reference is `docs/AI2_RUNTIME_ENV.example`; no `.env` or key was changed.
Adapter/base weights, approved labels, train/validation, receipts, journals, ACKs,
sealed benchmark and historical evaluation outputs retain their incoming hashes.
Integrity verification: 364 audited protected/history artifacts unchanged.

| Changed files | Behavior |
| --- | --- |
| conversation/config.py, environment.py | V3/V4 selector, explicit-path override, cache-only default, server OpenRouter settings; explicit CLI/backend .env loading |
| conversation/slm/qwen_lora.py, slm/router.py | Checkout-relative artifact paths; V4 base revision pin; cache-only load; lazy cache/locks/NF4/OOM behavior preserved |
| conversation/normalization.py, rule_parser.py, evidence.py | Exact sesame/milk aliases, bounded multi-allergy lists, retained-allergy turns/removal evidence, explicit minute guard, colleagues context, no deictic attribute invention |
| conversation/reference_resolver.py, parser.py | Actual selector mention preservation, no sentiment/similarity from plain numeric feedback, provider metadata/cost/attempts |
| conversation/providers/openrouter_provider.py, providers/base.py | Opt-in HTTP provider, wire schema, strict local JSON validation, bounded configurable retry/timeout, sanitized errors |
| conversation/models.py, conversation_logger.py, scripts/ai2_tools.py | Internal safe cost/attempt metadata, OpenRouter-key redaction |
| scripts/regress_ai2_adapters.py, tests/data/ai2_adapter_regressions.json | Same frozen authored probes for both adapters, direct output plus production replay, exact metrics/latency/overlap screening, no cloud calls |
| scripts/audit_ai2_repository.py | Read-only inventory, SHA256, git status, references, duplicate groups; proposal only |
| tests/test_ai2_adapter_integration.py, test_openrouter_provider.py, test_qwen_lora_provider.py, conftest.py | Offline safety/provider/loading/env/chain regressions, socket guards retained |
| tests/test_ai2_stability.py, test_ai2_preparation_review.py, test_schema_v02.py, test_v02_audit.py | Explicit unit-fixture routing adjustments described below; no benchmark/gold labels edited |
| docs/ai2_conversation.md, AI2_PREFERENCE_SCHEMA_V02.md and new audit/baseline/cleanup/env/handoff docs | Configuration, evidence, limits, archive plan and manifests |

Public common schemas and State Manager were not edited. AI1, AI3, backend ports,
frontend, dependencies and production defaults remain unchanged. AI1/pipeline
owners should review new canonical allergy aliases and unsupported downstream
constraint handling before a release; no PR or owner message was sent.

## Local model verification

Runtime Python 3.11.7: torch 2.14.1+cu130, transformers 5.19.0, peft 0.21.2,
bitsandbytes 0.50.2; GTX 1650 4096 MiB. Real loads: CUDA NF4, 196 quantized
linear layers, 392 LoRA parameter tensors, zero meta parameters. No OOM/CPU
fallback occurred in these runs; CPU fallback behavior is covered by mocks.

Base cache: Qwen/Qwen3-1.7B revision
`70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`. Base config is qwen3, 28 layers,
hidden_size=2048; both cached shard hashes match Kaggle upload copies.

| Adapter | Path | Weights SHA256 |
| --- | --- | --- |
| V3 rollback/default | models/ai2/ai2-qwen3-1.7b-lora-targeted-v3 | f255d954a9c2ea5cc8ecf203e255355045ff179fdb415ed848fe8628a8f3974f |
| Delivered experimental V4, opt-in | models/ai2/best_adapter_v4_experimental | a4711ce7a33236e31dfc3bc6ad48033fd4df9a80f40a60d11cc56ba6854aa6f1 |

Both: LoRA r=16, alpha=32, seven projection modules, 392 safetensors tensors,
Qwen2Tokenizer, EOS=151645, no-thinking generation template usable. V3 pad=151643,
V4 pad=151645: distinct preserved tokenizer artifacts, not rewritten for uniformity.
Full per-file checksums/config/tensor shapes are in `logs/v4-integration/model-audit.json`.
An additional final real load used `Qwen/Qwen3-1.7B` as the model ID (rather than
the resolved snapshot path) for both adapters, with sockets blocked and
local_files_only=true. Both passed CUDA NF4/materialization checks; evidence is
`logs/v4-integration/default-config-load.json`. No base files were downloaded.
These are observed local hashes; V4 has no supplied trusted upstream artifact
manifest or training/evaluation metrics in its folder. No new quality claims
or fabricated training metrics were created. Anticipated release folder is absent.

## Regression evidence

Baselines were captured **before** parser/evidence/runtime behavior patches on
the incoming dirty worktree, not a fresh Git HEAD or historical V3 benchmark.
Old reports remain intact. Baseline targeted tests: 182 passed. The 7 authored
probes cover sesame, milk+peanut, Wi-Fi-only update preserving allergies, 15-minute
travel, numeric feedback with references, context, unresolved deictic reference.

| Measurement (7 probes each) | V3 before | V4 before | V3 after real inference | V4 after real inference |
| --- | ---: | ---: | ---: | ---: |
| Complete JSON + public schema | 7 | 7 | 7 | 7 |
| Raw domain delta exact | 3 | 3 | 5 | 5 |
| Canonicalized raw domain delta exact | 3 | 3 | 5 | 5 |
| Effective pipeline delta exact | 2 | 2 | 7 | 7 |
| State exact | 2 | 2 | 7 | 7 |
| Hard constraints exact | 5 | 5 | 7 | 7 |
| References exact | 6 | 6 | 7 | 7 |
| Context / relative feedback / travel exact | 7 / 7 / 7 | 7 / 7 / 7 | 7 / 7 / 7 | 7 / 7 / 7 |
| Cold load + first generation, seconds | 72.0 | 74.0 | 75.6 | 83.3 |
| Warm generation mean, seconds (6 probes) | 22.7 | 22.3 | 26.7 | 22.6 |

Exact comparison is strict: full nine-field domain dictionaries/list order,
including canonical references/IDs for the effective target. Raw selector-to-ID
representation differences also fail raw exact; this is a diagnostic measure,
not a standalone model semantic-accuracy score. JSON validity is not safety.
No meaningful p95 or general latency/quality estimate follows from seven probes.
Latency includes concurrent offline testing/Windows conditions; cold includes load.

After real generation, a final validator-only fix removed an erroneous access to
a nonexistent travel-time form field. The **same preserved outputs** were replayed
through final code (`v3-final-replay.json`, `v4-final-replay.json`), retaining 7/7
delta/state exact and accepting the correct 15-minute output without fallback.
Final replay has one rejected SLM result per adapter (invented food `quán` on
unresolved `Quán đó nhé`); it retains the unresolved reference and requests
clarification. Replay timings do not represent new GPU generation.

Observed failures and attribution:

- V3 initially maps sesame to peanut; V4 initially returns untranslated mè.
  Exact aliases/rules preserve sesame; observable contradictions fail validation.
- Both initially return milk+peanut in the reverse order, with both present.
  Missing-second-allergen behavior is additionally tested with mocked output;
  rules retain both targets. No claim that these probes observed an actual omission.
- Wi-Fi update output itself was correct; AI2 evidence validation incorrectly
  required a fresh allergy delta for a retained-allergy statement. State Manager
  was not the cause. Malicious allergy removals now have separate regressions.
- V4 numeric feedback omitted mention; deterministic caller selectors supply it.
  Both invent positive sentiment on plain cheaper feedback; the bounded resolver
  drops it, with no invented amenity/ID/similarity. Other general model hallucinations
  remain outside this bounded validation guarantee.
- Standalone unresolved reference models invent food=[quán]; rejected, clarification
  preserved. Intentional unresolved cases must not be treated as retrieval requests.
- Context and 15-minute state were understood; final acceptance metadata is covered
  by service tests and final replay. No time-to-distance conversion is invented.

AI1/AI3 were never invoked in adapter diagnostics. Real allergen filtering and ETA
support downstream are owner responsibilities; interface/unit tests do not prove
those source-data attributes exist or enforce complete safe recommendations.

Train/validation screening scanned exactly 1.246 records from preserved experimental
QA train_sft/validation_sft (hashes in reports). No exact overlap and no similarity
>=.85 for these 7 new probe messages (maximum about .621). Lexical screening does
not prove semantic/family independence; related topics exist in training. These
are authored runtime regressions, **not an independent reviewed benchmark**.
Validation used to choose the checkpoint is never evaluated as independent gold.
Sealed benchmark prompts and labels were not opened. A larger externally reviewed
independent suite and family-level overlap signoff remain pending.

Offline regression adjustments are explicit: add unparsed ambience to a soft-allergen
mock-routing test so the newly complete rules still exercise invalid output/fallback;
accept rule bypass after rejecting a bad translation of English milk allergy; use
explicit residual `shellfish` in two hybrid-union unit fixtures instead of expecting
model narrowing of fully parsed broad `hải sản`. Expected union values are retained.
No historical benchmark/test data file or approved gold was relabeled.

## Configuration and rerun

Final validation: **1659 passed, 35 skipped**, Python 3.11.7, full suite with
`scripts.sealed_benchmark_guard` (294.70 s). The skips retain sealed/optional
environment protections. `examples/integration_demo.py` passed afterward using
real AI2 plus explicitly synthetic AI1/AI3; it measures contracts, not their quality.
Public canonical imports and src.conversation alias identity passed; 13 changed
runtime/tool modules parsed successfully; git diff --check passed. Full output:
`logs/v4-integration/full-tests-confirmed.txt` (PowerShell UTF-16 log).

An intermediate run detected runtime hashes changing during test execution;
the candidate-snapshot guard correctly rejected the stale test fixture. No guard
or historical receipt was loosened. The final full run used frozen source and
passed. Historical candidate snapshots should continue to reject current changed
runtime; use preserved experimental/toolkit packages for training reproducibility,
not refreshed gold/receipts or new inputs to bypass that guard.

Leave defaults at `LOCAL_SLM_ENABLED=false`, adapter version v3, Gemini fallback.
For an explicit local V4 deployment/test:

```powershell
$env:LOCAL_SLM_ENABLED = 'true'
$env:LOCAL_SLM_ADAPTER_VERSION = 'v4'
Remove-Item Env:LOCAL_SLM_ADAPTER_PATH -ErrorAction SilentlyContinue
$env:LOCAL_SLM_LOCAL_FILES_ONLY = 'true'
```

The explicit path has priority; if an existing .env supplies the V3 path, set
`LOCAL_SLM_ADAPTER_PATH=models/ai2/best_adapter_v4_experimental` explicitly instead.
Rollback: version=v3 (with no explicit override), or explicit V3 path. Restart the
backend between adapter switches to release GPU memory. No defaults were activated.

Run one adapter per process, fresh output filenames; network is blocked:

```powershell
.\.venv-fullstack\Scripts\python.exe scripts/regress_ai2_adapters.py --run-model --adapter models/ai2/ai2-qwen3-1.7b-lora-targeted-v3 --output logs/v4-integration/new-v3.json --corpus data/ai2_labeling/v4/experimental_qa_02/data/data/train_sft.jsonl --corpus data/ai2_labeling/v4/experimental_qa_02/data/data/validation_sft.jsonl
.\.venv-fullstack\Scripts\python.exe scripts/regress_ai2_adapters.py --run-model --adapter models/ai2/best_adapter_v4_experimental --output logs/v4-integration/new-v4.json --corpus data/ai2_labeling/v4/experimental_qa_02/data/data/train_sft.jsonl --corpus data/ai2_labeling/v4/experimental_qa_02/data/data/validation_sft.jsonl
```

Omit --run-model/--adapter for rules only. --replay-report reuses preserved SLM
outputs, never expected labels, checks case hashes and does no inference. Reports
will not overwrite an existing output path. The incomplete HF snapshot lacks
non-runtime documentation files; harness resolves cached config's parent instead
of demanding a complete snapshot/redownloading the base.

For OpenRouter **later**, after key/credits and deployment approval:
`OPENROUTER_ENABLED=true`, `LLM_PROVIDER=openrouter`, server-only key,
`OPENROUTER_MODEL=qwen/qwen3-32b` or `deepseek/deepseek-v3.2`. Default timeout=30,
retry=0, tokens=1024; schema mode opt-in after endpoint compatibility check. See
[provider audit](AI2_OPENROUTER_AUDIT.md) and [official structured-output support](https://openrouter.ai/docs/guides/features/structured-outputs).
No live compatibility, latency or bill was measured; mocked costs are test data.

## Freeze considerations and cleanup

AI2 bounded regression fixes are ready for review; adapters remain opt-in. Pending:
trusted V4 training/evaluation manifest, larger reviewed independent evaluation,
broader multi-turn/negation/reference semantics and downstream hard-filter/ETA
coverage. Raw feedback/deictic errors remain observable, mitigated for tested patterns.
Gemini SDK-specific error classification is still its prior generic policy; live
provider/model compatibility is untested. Long prompts/concurrency/VRAM limits
were not stress-tested; production should serialize inference on the 4 GB GPU.

Cleanup is proposal only: [plan](REPOSITORY_CLEANUP_PLAN.md),
[19-entry archive manifest](REPOSITORY_ARCHIVE_MANIFEST.json). Initially about 1.13 GB;
after new test outputs the audit identifies about **1.55 GB** of cache/external-archive
candidates, subject to approval. Dataset
provenance, historical ZIPs and model rollback artifacts have not moved.
