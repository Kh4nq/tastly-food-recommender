# AI2 SLM data labeling (PreferenceUpdate 0.2)

This is a local candidate-labeling and human-review workflow. It does not train,
select, download, or run an SLM. Teacher predictions are **not ground truth**.
Only a person's explicit Accept or Correct decision can become an export target;
even reviewed labels remain subject to deterministic checks and human error.

## Architecture and contracts

```text
Independent Vietnamese templates / imported PromptSample JSONL
  -> held-out exclusion + exact/normalized deduplication
  -> existing rule parser + production routing metadata (SLM forced off)
  -> optional existing Gemini adapter, only when routing requests assistance
  -> deterministic validation + priority queue
  -> STOP: local human review
  -> revalidation + accepted/corrected-only export
```

Implementation lives in `src/conversation/labeling/`; the seven scripts are thin
entry points. Canonical `common.schemas.PreferenceUpdate`, `UserPreferenceState`,
`Candidate`, and `PreviousResult` are reused without changes. Production AI2
parsing handles normalization, rule/model precedence, and reference resolution.
Synthetic multi-turn context uses the existing rule parser and StateManager.
Mock candidates retain restaurant/menu/dish IDs in `mock_candidates`; the
explicit projection into AI2's existing `PreviousResult` retains its supported
restaurant/menu IDs and rank. No retrieval or ranking is called.

Candidate normalization uses AI2's shared exact-alias tables before validation
and review, including cuisine/context, known ambience/dislike labels and peanut
exclusions. Original teacher predictions remain separate audit evidence. Food
names (`mì quảng`), unknown cuisines and free text are not translated into enums.
Validation rejects known noncanonical aliases or duplicates in these fields;
it does not claim that unknown text is semantically correct. Existing reviewed
artifacts are never rewritten: a legacy noncanonical label requires an explicit
correction before export. Accepted/corrected-only export gates are unchanged.

Rules consume category words only with matching recognized spans, then remove
safe filler. Meaningful residual wording still requests inference. Reducing calls
must preserve semantic recall, especially negation, conditions and corrections.
Run `python scripts/audit_ai2_routing.py` for a deterministic, independent
240-prompt rule-only audit and 30 normalization probes; `--details` includes
spans, residuals, updates, expectations and diagnostic flags. Redirect generated
reports to an ignored directory such as `.pytest_cache/`; do not commit them.
This diagnostic never reads the held-out benchmark and is not a quality estimate
for real user traffic. Keep its pool/seed fixed when comparing revisions.

## Artifacts

Default directory: `data/ai2_labeling/` (relative defaults resolve to the checkout,
even when a script is launched elsewhere). Its contents are ignored recursively
except `.gitkeep`. Choose a separate directory for every independent run.

| Artifact | Contents |
| --- | --- |
| `prompt_pool.jsonl` | `sample_id`, category, message, current_state, previous_results, source, generation seed/version/hash; optional history and mock_candidates; no labels |
| `teacher_labels.jsonl` | Original rule_result, normalized rule_candidate, rule_resolved, production routing metadata, original teacher_prediction, normalized candidate, provider/model/latency/error/attempt status |
| `validation.jsonl` | sample_id, passed, errors, warnings, risk_flags |
| `review_queue.jsonl` | Full sample, teacher record, validation, disagreement, high/medium/low priority |
| `reviewed.jsonl` | Decision history: original teacher prediction and candidate, final_label, accepted/corrected/rejected/skipped action, note, UTC timestamp, queue-item fingerprint |
| `training_v02.jsonl` | schema_version="0.2", input (message/current_state/rule_result/previous_results), target (canonical PreferenceUpdate), metadata (sample_id/category/source/review_status/rule_resolved/review_timestamp) |
| `*.excluded.jsonl` | Excluded IDs and reason codes; prompt hashes when filtering pools; no copied benchmark text |

The new training envelope uses `current_state` and `metadata.review_status`.
The older `check_ai2_slm_dataset.py` checks the historical interactive export
envelope (`old_state`, `label_status`); it is not the validator for these artifacts.
Use this pipeline's validation and export gates. Historical logs are not imported
or relabeled automatically.

## Offline start and review

From the repository root, using Python 3.11+ in the project environment:

```powershell
python scripts/prepare_ai2_slm_data.py --count 200 --seed 42 --provider rule
python scripts/build_ai2_review_queue.py --stats
python -m pip install -e ".[labeling]"
python -m streamlit run scripts/review_ai2_labels.py --server.address 127.0.0.1 --browser.gatherUsageStats false
python scripts/export_ai2_training_set.py --only-unresolved
```

`--dry-run` (alias `--offline`) forces the rule provider even if `--provider gemini`
is supplied, creates reviewable artifacts, and stops before human review/export.
It does not load `.env`. Example for a separate 20-prompt smoke directory:

```powershell
python scripts/prepare_ai2_slm_data.py --count 20 --seed 42 --dry-run --directory data/ai2_labeling/smoke
python -m streamlit run scripts/review_ai2_labels.py --server.address 127.0.0.1 --browser.gatherUsageStats false -- --directory data/ai2_labeling/smoke
python scripts/export_ai2_training_set.py --directory data/ai2_labeling/smoke --only-unresolved
```

The UI displays input/context/results, rule output, original teacher output,
normalized candidate, validation, routing, and priority. Accept uses the candidate;
Correct validates the edited JSON and semantic invariants before saving. Reject
and Skip have no target. Failed teacher attempts require Correct, never Accept.
Previously reviewed/skipped items can be revisited using the checkboxes. All
decisions are retained; the latest explicit decision controls export. This is a
single-machine review tool without reviewer authentication or multi-user merging.

## Individual stages and optional Gemini

```powershell
python scripts/generate_ai2_prompt_pool.py --count 200 --seed 42
python scripts/teacher_label_ai2.py --provider rule
python scripts/validate_ai2_labels.py
python scripts/build_ai2_review_queue.py
python scripts/export_ai2_training_set.py
```

Generator options `--single-turn` and `--no-previous-results` disable optional
context fixtures. Every CLI has `--directory`; individual stages also offer
`--output`, with `--pool`, `--labels`, `--queue`, or `--reviewed` as applicable.
Imported pools must follow the same PromptSample schema. Generation is seeded
and independent of benchmark contents. Filtering can reduce the requested count;
the printed summary and exclusion report explain the retained count. Very large
requests can exhaust the finite template space; this is not a natural-language
distribution or a quality benchmark.

Only when you explicitly want paid teacher calls, install the existing Gemini
extra, supply `GEMINI_API_KEY` and `GEMINI_MODEL` through the environment or the
existing untracked `.env`, and use a **new run directory**:

```powershell
python -m pip install -e ".[gemini]"
python scripts/prepare_ai2_slm_data.py --count 200 --seed 42 --provider gemini --directory data/ai2_labeling/gemini_run
```

This command can make one call for each unresolved sample. No live calls were
used to develop or test the pipeline. Rule-resolved samples never call Gemini.
Rule-only unresolved candidates remain partial and require careful review.

The one-external-call-per-sample cap takes precedence over retries: retry budget
is **zero**, including timeouts/rate limits. Only those transient errors get
`retryable=true` as diagnostic metadata; there is no automatic retry command.
Provider failure leaves `candidate=null`, with a bounded error code, never a
successful rule fallback label. No exception body or API key is printed.

## Resume and preservation

Rerun the same command with the same directory, seed, count, and provider.
Teacher IDs already present in the journal are not relabeled. A full sample
fingerprint includes context/results/history, preventing reuse after input edits.
Changing provider or sample content requires a new run directory. Existing pools,
queues, and training exports cannot be replaced with different content implicitly;
use a new output path when rebuilding an export after more reviews.

The teacher journal atomically reserves an attempt before provider initialization
or invocation. An interruption leaves `attempt_reserved` and no candidate. Resume
does not call that sample again, because a timeout/crash cannot prove that the
provider did not process the request. Correct or reject it manually. A hard process
kill can leave a `.lock`: inspect the journal, stop any other writer, then remove
only that stale lock before resuming. Review writes are atomic snapshots retaining
the complete decision history. Queue-item fingerprints invalidate stale reviews.

## Isolation and validation limits

`benchmarks/ai2_vietnamese_prompts.jsonl` is held out and is never rewritten,
used to generate prompts, or teacher-labeled for training. Its messages are read
only to form an exclusion index. Existing Unicode/case/whitespace normalization
is reused, punctuation is normalized, and SHA-256 prompt hashes detect overlap.
Both current messages and supplied history are checked. Exact/normalized pool
duplicates and duplicate IDs are reported; filtering keeps the first safe row.
Validation/export reject all remaining duplicates. The exporter checks the
benchmark again, schema and semantic invariants, review provenance, and current
rule routing. Unreviewed/rejected/skipped/invalid/leaking samples cannot export.

Validation covers closed structural fields, transport/parking evidence, hard/soft
precedence, absolute/relative conflicts, known allergy exclusions, relative events
in context, canonical removals, and references against caller-owned IDs. Arbitrary
constraint/context keys remain extensible. Unknown semantics and unsupported
allergens require human judgment. Normalized equality does not detect paraphrase
leakage or all possible benchmark-derived context: imported pools must have
independent provenance. Hashes and review records are audit aids, not signatures
or proof of identity. Do not manually mark machine labels reviewed.

High priority includes failures, rule/teacher disagreement, references, correction,
feedback, allergies, absolute/relative conflicts, and ambiguous semantics. A
passing validator is not a claim of semantic completeness or model quality.

## Verification

```powershell
python -m pytest -q tests/test_ai2_labeling.py tests/test_ai2_labeling_ui.py
python -m pytest -q
python examples/integration_demo.py
```

Tests use tiny synthetic fixtures in `tests/data/ai2_labeling_samples.jsonl`, fake
providers, and the repository's socket guards. UI tests use optional Streamlit
AppTest and skip when the extra is absent. No test needs API keys, models, datasets,
or network access. There is no SLM training or inference implementation here.

Implementation verification (2026-09-30): after installing missing test dependencies,
the existing baseline was 641 passed / 1 failed; final full suite was 702 passed /
1 failed, including all 61 new labeling/UI cases. The unchanged failure is
`test_production_defaults_fail_clearly_without_fabrication`: production retrieval
attempts to open absent `data/processed/restaurants.parquet` before the expected
AI3 error. No AI1 data or implementation was changed to mask it. The integration
demo passed. A 20-prompt offline run produced 19 passing candidates and one review
failure; its unreviewed export contained zero records. Exact/normalized held-out
probes and rejected/unreviewed export exclusions were verified. External teacher
API calls: zero. Installed test/UI libraries are not SLM models or checkpoints.
