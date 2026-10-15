> Historical development report. Use the [public README](../README.md) and [setup guide](setup.md) for the current distribution.

# AI 2 v0.2 migration report

## Verification

| Run | Total | Passed | Failed |
| --- | ---: | ---: | ---: |
| Baseline, verified offline | 469 | 469 | 0 |
| After migration, full pytest | 537 | 537 | 0 |

Command: `.venv/Scripts/python.exe -m pytest -q`.
All tests block network connections; provider tests use fake SDK endpoints or
local mock transports. There were no dependency installations.

## Schema migration

- PreferenceUpdate adds context_updates={}, with primitive/list values and
  canonical known fields. Location remains top-level.
- Context deltas merge into an independent state snapshot. Transport does not
  infer parking; explicit hard/soft parking wording wins over model inference.
- Canonical removal paths are supported. Unambiguous legacy numeric removal
  keys still work; other legacy labels retain their existing meaning.
- Relative directions remain in the current turn update. State transitions
  purge context.relative_updates from old snapshots instead of accumulating it.
- Absolute settings suppress relative directions; hard values suppress redundant
  soft values. Removals retain precedence over additions; explicit forms retain
  their existing priority. Explicit natural-language corrections remain supported.
- Both providers use the same structured projection and v0.2 target.
- Interactive output/corrections support context. Saved records and exports use
  schema_version="0.2". Legacy targets gain context_updates={} without changing
  their semantic labels or review status.

Intentional old-test migrations cover relative non-persistence, absolute priority,
canonical removal output, date context, deterministic parking, rejection of
invented parking, and versioned exports. The original 469 test cases remain in
the suite; 68 new cases cover the migration and SLM boundary.

## Frozen SLM

Defaults: LOCAL_SLM_ENABLED=false, LOCAL_SLM_BACKEND=disabled,
LOCAL_SLM_MODEL="", LOCAL_SLM_MIN_CONFIDENCE=0.80.

Sufficient rules bypass both inference layers. Unresolved input goes directly to
the external provider while SLM is disabled. This path never imports SLM modules,
loads model files, or initializes a local runtime. When enabled, the router accepts
only validated results meeting the confidence threshold and not requesting
fallback. Invalid, uncertain and failed results fall back to the external provider.
Enabling the disabled backend safely reports disabled_backend.

The input/result contracts and backend factory are ready for future implementation;
no real inference or training exists. Metadata and interactive display expose SLM
status independently of the external provider. The dataset checker only validates
reviewed exports and reports distribution, duplicates and field frequencies.

## Mock/rule benchmark

Artifact: [ai2_mock_schema_v02.json](../benchmarks/results/ai2_mock_schema_v02.json).
The benchmark ran with explicit mock configuration, SLM disabled and sockets blocked.

- 105 prompts, 15 categories; 30 rule-only (28.57%), 75 empty mock fallback calls.
- 36/54 evaluated prompts met all frozen expectations; 80/98 checked fields matched.
- 0 API errors and 0 validation errors. Empty mock inference cannot resolve
  unknown semantics, so these figures are not model-quality measurements.
- Comparable first-per-category subset: 7/15 (46.67%) previously, 8/15 (53.33%) now.
  The comparison uses the existing September 28 mock report, not a reconstructed baseline.
- Evaluator unchanged. Historical benchmark expectations remain frozen.

Benchmark source SHA-256, identical before and after:
`3067D0B66E9F0D16DB316A1DAB766406C115C936B78133F200E370C6B434E5C8`.

## Files created

- src/conversation/context.py
- src/conversation/slm/__init__.py
- src/conversation/slm/base.py
- src/conversation/slm/disabled.py
- src/conversation/slm/router.py
- scripts/check_ai2_slm_dataset.py
- tests/test_schema_v02.py
- docs/AI2_PREFERENCE_SCHEMA_V02.md
- docs/AI2_V02_MIGRATION_REPORT.md
- benchmarks/results/ai2_mock_schema_v02.json

## Files modified

- README.md
- src/common/schemas.py
- src/conversation/config.py
- src/conversation/models.py
- src/conversation/normalization.py
- src/conversation/parser.py
- src/conversation/prompts.py
- src/conversation/rule_parser.py
- src/conversation/service.py
- src/conversation/state_manager.py
- src/conversation/providers/structured.py
- src/conversation/interactive/cli.py
- src/conversation/interactive/dataset_logger.py
- src/conversation/interactive/session.py
- tests/conftest.py
- tests/data/conversation_cases.json (unit fixtures; not benchmark samples)
- tests/test_conversation.py
- tests/test_conversation_mvp.py
- tests/test_extensible_constraints.py
- tests/test_interactive_ai2.py
- tests/test_openai_provider.py

## Execution confirmations

- LOCAL_SLM_ENABLED default = false.
- Actual SLM model calls = 0; SLM training runs = 0.
- Gemini real calls = 0; OpenAI real calls = 0.
- Model downloads = 0; torch/transformers installations = 0.
- Benchmark dataset unchanged; AI1/AI3 modules unchanged.
- Provider network and retry implementations unchanged.
