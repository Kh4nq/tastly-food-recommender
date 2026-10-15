"""Authored diagnostic regressions, never checkpoint-selection/benchmark gold.

Default is rules only. --run-model explicitly enables local, cache-only NF4.
One adapter per process releases VRAM between V3/V4. Cloud calls are forbidden.
"""
from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import socket
import sys
from time import perf_counter
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from common.schemas import PreferenceUpdate, UserPreferenceState, UserRequest
from conversation.config import ConversationConfig
from conversation.normalization import normalize_update
from conversation.rule_parser import parse_by_rules_detailed
from conversation.service import process_user_request
from conversation.slm.base import SLMInput
from conversation.slm.base import SLMParseResult
from conversation.slm.qwen_lora import QwenLoRAProvider, parse_response

DEFAULT_CASES = ROOT / "tests/data/ai2_adapter_regressions.json"


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def overlap_audit(cases, corpora):
    """Screen exact/near messages; similarity flags require review, not relabeling.

    Do not open the sealed benchmark. Include both train and validation to prevent
    accidentally marketing checkpoint-selection validation as independent testing.
    """
    messages = []
    for path in corpora:
        if path.name == "ai2_vietnamese_prompts.jsonl":
            raise ValueError("Sealed benchmark must not be inspected")
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            row = json.loads(line)
            if "input_text" in row:
                row = json.loads(row["input_text"].split("\n", 1)[1])
            message = row.get("message") or row.get("sample", {}).get("message")
            if isinstance(message, str):
                messages.append((str(path), " ".join(message.lower().split())))
    checks = []
    for case in cases:
        text = " ".join(case["message"].lower().split())
        best = max(((SequenceMatcher(None, text, m, autojunk=False).ratio(), p)
                    for p, m in messages), default=(0, None))
        checks.append({"id": case["id"], "max_message_similarity": best[0],
                       "source": best[1], "exact_overlap": best[0] == 1,
                       "near_overlap": best[0] >= .85})
    return {"corpora": [{"path": str(p), "sha256": sha256(p)} for p in corpora],
            "messages_scanned": len(messages), "threshold": .85, "cases": checks,
            "independent_benchmark": False,
            "limitation": "Authored runtime probes; lexical screening does not prove semantic independence."}


def run_case(case, local=None):
    request = UserRequest(session_id="adapter-regression", message=case["message"],
                          current_state=case.get("current_state"),
                          previous_results=case.get("previous_results", []))
    expected_delta = PreferenceUpdate.model_validate(case["expected_update"])
    expected_state = UserPreferenceState.model_validate(case["expected_state"])
    raw = result = None
    inference_ms = None
    valid = raw_exact = canonical_exact = None
    if local is not None:
        start = perf_counter()
        result = local.parse(SLMInput(message=request.message, current_state=request.current_state,
                            previous_results=request.previous_results,
                            rule_result=parse_by_rules_detailed(request.message)))
        inference_ms = (perf_counter() - start) * 1000
        raw = local.last_response
        try:
            delta = parse_response(raw)
            valid = True
            raw_exact = delta.model_dump() == expected_delta.model_dump()
            canonical_exact = normalize_update(delta, request.current_state) == expected_delta
        except (ValueError, TypeError):
            valid = raw_exact = canonical_exact = False
    # Replay the one real generation through production validation/merge/state.
    # No expected answer is ever injected as an inference response.
    turn = process_user_request(request, config=ConversationConfig(
        llm_provider="none", local_slm_enabled=local is not None, log_enabled=False),
        slm_provider=SimpleNamespace(parse=lambda _: result.model_copy(deep=True)) if result else None)
    actual = turn.state
    expected_allergy = set(expected_state.hard_constraints.get("allergens_excluded", []))
    actual_allergy = set(actual.hard_constraints.get("allergens_excluded", []))
    checks = {
        "json_schema_valid": valid, "raw_delta_exact": raw_exact,
        "canonical_raw_delta_exact": canonical_exact,
        "effective_delta_exact": turn.preference_update == expected_delta,
        "state_exact": actual == expected_state,
        "allergy_missing": sorted(expected_allergy - actual_allergy),
        "allergy_extra": sorted(actual_allergy - expected_allergy),
        "hard_constraints_exact": actual.hard_constraints == expected_state.hard_constraints,
        "reference_exact": actual.reference_restaurants == expected_state.reference_restaurants,
        "context_exact": actual.context == expected_state.context,
        "feedback_exact": turn.preference_update.relative_updates == expected_delta.relative_updates,
        "travel_time_exact": actual.hard_constraints.get("max_travel_time_min") == expected_state.hard_constraints.get("max_travel_time_min"),
    }
    attribution = ("covered" if checks["state_exact"] and checks["effective_delta_exact"] else
                   "rules_or_ai2_merge" if local is None or not turn.metadata.slm_called else
                   "ai2_inference_or_validation")
    return {"id": case["id"], "message": case["message"], "checks": checks,
            "attribution": attribution, "ai1_ai3_called": False,
            "inference_ms": inference_ms, "replay_ms": turn.metadata.total_ms,
            "raw_response": raw, "slm_result": result.model_dump(mode="json") if result else None,
            "result": turn.model_dump(mode="json")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--adapter", type=Path)
    parser.add_argument("--base", default="Qwen/Qwen3-1.7B")
    parser.add_argument("--run-model", action="store_true")
    parser.add_argument("--replay-report", type=Path, help="Replay preserved raw results, no model inference")
    parser.add_argument("--corpus", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Output already exists; use a new report path to preserve baseline")
    if args.run_model and not args.adapter:
        parser.error("--run-model requires --adapter")
    if args.run_model and args.replay_report:
        parser.error("Choose real inference or preserved replay")
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    report = {"cases_sha256": sha256(args.cases), "kind": "authored_diagnostic_not_independent_benchmark",
              "external_api_calls": 0, "adapter": str(args.adapter) if args.adapter else None,
              "overlap": overlap_audit(cases, args.corpus), "cases": []}
    report["source_checksums"] = {p.relative_to(ROOT).as_posix(): sha256(p)
        for p in (ROOT / "src/conversation").rglob("*.py")}
    replay = None
    if args.replay_report:
        prior = json.loads(args.replay_report.read_text(encoding="utf-8"))
        if prior["cases_sha256"] != report["cases_sha256"]:
            parser.error("Replay cases checksum differs from preserved baseline")
        replay = {c["id"]: c for c in prior["cases"]}
        if set(replay) != {c["id"] for c in cases}:
            parser.error("Replay baseline is incomplete")
        report["replay_source"] = {"path": str(args.replay_report), "sha256": sha256(args.replay_report)}
        report["adapter"] = prior["adapter"]
    def forbid(*_, **__):
        raise RuntimeError("Network forbidden in adapter regression")
    socket.socket.connect = forbid
    socket.create_connection = forbid
    local = None
    if args.run_model:
        # Existing runtime has no cache-only flag yet; use resolved cache directory
        # so even the pre-patch baseline cannot fetch/re-download model files.
        base = Path(args.base)
        if not base.is_dir():
            from huggingface_hub import hf_hub_download
            base = Path(hf_hub_download(args.base, "config.json", local_files_only=True)).parent
        report["base_snapshot"] = str(base)
        report["adapter_checksums"] = {p.name: sha256(p) for p in args.adapter.iterdir() if p.is_file()}
        local = QwenLoRAProvider(str(base), str(args.adapter))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    def save():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for case in cases:
        print(case["id"], flush=True)
        selected = local
        if replay is not None:
            old = replay[case["id"]]
            selected = SimpleNamespace(last_response=old["raw_response"], parse=lambda _, row=old:
                SLMParseResult.model_validate(row["slm_result"]))
        record = run_case(case, selected)
        if replay is not None:
            record["inference_ms"] = None
        report["cases"].append(record)
        report["load_summary"] = local.load_summary if local else None
        report["load_error"] = local.last_load_error if local else None
        save()
        if local and local.last_load_error:
            report["stopped"] = "load_failed; remaining model probes not run"
            save()
            return 2
    report["summary"] = {key: sum(c["checks"][key] is True for c in report["cases"])
                         for key in report["cases"][0]["checks"] if not isinstance(report["cases"][0]["checks"][key], list)}
    save()
    print(json.dumps(report["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
