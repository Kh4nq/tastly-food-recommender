"""Offline Rule/raw/guarded V3/V4 diagnostics; one adapter per process.

Default dry-run. Use --run-local explicitly; no external provider is reachable.
Dataset expectations are frozen and hashed before model generation.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import socket
import sys
from time import perf_counter
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from common.schemas import UserRequest
from conversation.config import ConversationConfig
from conversation.parser import _state_for_inference
from conversation.preprocessing import prepare_input
from conversation.rule_parser import parse_by_rules_detailed
from conversation.service import process_user_request
from conversation.slm.base import SLMInput, SLMParseResult
from conversation.slm.qwen_lora import QwenLoRAProvider, parse_response, _unique_object, _invalid_constant
from scripts.ai2_benchmark_metrics import raw_stages, score, summary

DEFAULT_SUITE = ROOT / "tests/data/ai2_freeze_diagnostics_20261015.json"


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_hashes():
    paths = sorted((ROOT / "src/conversation").rglob("*.py")) + [ROOT / "src/common/schemas.py"]
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in paths}


def forbid_sealed(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = Path(args[0].decode() if isinstance(args[0], bytes) else args[0]).resolve()
        if path.is_relative_to(ROOT / "benchmarks"):
            raise PermissionError("Sealed benchmark and historical benchmark outputs are not opened")


@contextmanager
def offline_network():
    def forbidden(*_, **__):
        raise RuntimeError("External inference/downloads are forbidden in local benchmark")
    connect, create = socket.socket.connect, socket.create_connection
    socket.socket.connect, socket.create_connection = forbidden, forbidden
    try:
        yield
    finally:
        socket.socket.connect, socket.create_connection = connect, create


def request_for(case):
    return UserRequest(session_id="adapter-regression", message=case["message"],
                       current_state=case.get("current_state"), previous_results=case.get("previous_results", []))


def input_for(request, config):
    prepared = prepare_input(request, config, None)
    return SLMInput(message=prepared.message, current_state=_state_for_inference(request),
                    rule_result=parse_by_rules_detailed(prepared.message),
                    previous_results=request.previous_results)


def evaluate_case(case, local=None, *, replay=None):
    request = request_for(case)
    config = ConversationConfig(llm_provider="none", log_enabled=False, local_slm_enabled=False)
    rule = process_user_request(request, config=config)
    inp = input_for(request, config)
    record = {"id": case["id"], "category": case["category"], "label_status": case["label_status"],
              "message": case["message"], "input": inp.model_dump(mode="json"),
              "history_used_for_audit_only": case.get("history", []),
              "rule": rule.model_dump(mode="json"), "ai1_ai3_database_called": False,
              "scores": {"rule": score(case, rule.preference_update, rule.state)},
              "raw_response": None, "slm_result": None, "generation_ms": None,
              "json_valid": None, "schema_valid": None}
    parsed = None
    result = None
    if local is not None or replay is not None:
        start = perf_counter()
        result = SLMParseResult.model_validate(replay["slm_result"]) if replay is not None else local.parse(inp)
        record["generation_ms"] = None if replay is not None else (perf_counter() - start) * 1000
        record["raw_response"] = replay["raw_response"] if replay is not None else local.last_response
        record["slm_result"] = result.model_dump(mode="json")
        try:
            json.loads(record["raw_response"], object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
            record["json_valid"] = True
        except (ValueError, TypeError, RecursionError):
            record["json_valid"] = False
        try:
            parsed = parse_response(record["raw_response"])
            record["schema_valid"] = True
        except (ValueError, TypeError, RecursionError):
            record["schema_valid"] = False
        raw = raw_stages(case, parsed)
        record["scores"].update(raw=raw["raw"], canonical=raw["canonical"])
        record["model_only_state_projection"] = raw["projected_state"]
        record["projection_error"] = raw["projection_error"]
        # Replay production route with the exact same output; deterministic rules
        # can bypass the replay. Expectations are NEVER injected as model answers.
        selected = SimpleNamespace(parse=lambda _: result.model_copy(deep=True))
        effective = process_user_request(request, config=ConversationConfig(
            llm_provider="none", local_slm_enabled=True, log_enabled=False), slm_provider=selected)
        record["effective"] = effective.model_dump(mode="json")
        record["scores"]["effective"] = score(case, effective.preference_update, effective.state)
        record["guard_changed_delta"] = parsed is not None and effective.preference_update != parsed
        record["production_generation_ms"] = record["generation_ms"] if effective.metadata.slm_called else 0
    else:
        record["scores"].update(raw=None, canonical=None, effective=None)
    return record


def write_report(path, report):
    # Checkpoint is this run's newly-created output, not a historical artifact.
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=["dry-run", "rules", "local", "replay"], default="dry-run")
    parser.add_argument("--adapter", choices=["v3", "v4"])
    parser.add_argument("--run-local", action="store_true")
    parser.add_argument("--replay-report", type=Path)
    parser.add_argument("--case-id", action="append", help="Explicit diagnostic subset; never changes frozen labels")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Do not overwrite reports; choose a fresh output filename")
    if args.mode == "local" and (not args.run_local or not args.adapter):
        parser.error("Local inference requires --run-local and --adapter")
    if args.mode == "replay" and not args.replay_report:
        parser.error("Replay requires --replay-report")
    sys.addaudithook(forbid_sealed)
    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    all_ids = {c["id"] for c in suite["cases"]}
    if args.case_id:
        if not set(args.case_id) <= all_ids:
            parser.error("Unknown frozen case ID")
        suite = {**suite, "cases": [c for c in suite["cases"] if c["id"] in set(args.case_id)]}
    report = {"mode": args.mode, "suite_sha256": sha256(args.suite), "suite_kind": suite["kind"],
              "independent_gold_count": 0, "source_checksums": source_hashes(),
              "decoding": {"max_new_tokens": 512, "do_sample": False, "num_beams": 1,
                           "repetition_penalty": 1.0, "enable_thinking": False},
              "external_api_calls": 0, "cases": []}
    report["selected_case_ids"] = [c["id"] for c in suite["cases"]]
    report["complete_suite"] = len(suite["cases"]) == len(all_ids)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.mode == "dry-run":
        report["planned_case_ids"] = [c["id"] for c in suite["cases"]]
        write_report(args.output, report)
        print(f"DRY RUN: {len(suite['cases'])} cases planned, no model/provider loaded")
        return 0
    replay = {}
    if args.mode == "replay":
        prior = json.loads(args.replay_report.read_text(encoding="utf-8"))
        if prior["suite_sha256"] != report["suite_sha256"]:
            parser.error("Frozen suite checksum differs from replay input")
        replay = {c["id"]: c for c in prior["cases"]}
        if set(replay) - all_ids or not {c["id"] for c in suite["cases"]} <= set(replay):
            parser.error("Replay input is incomplete")
        report["replay_sha256"] = sha256(args.replay_report)
    with offline_network():
        local = None
        if args.mode == "local":
            path = ROOT / "models/ai2" / ("ai2-qwen3-1.7b-lora-targeted-v3" if args.adapter == "v3" else "best_adapter_v4_experimental")
            report["adapter"] = args.adapter
            report["adapter_checksums"] = {p.name: sha256(p) for p in path.iterdir() if p.is_file()}
            start = perf_counter()
            import torch
            report["runtime_import_ms"] = (perf_counter() - start) * 1000
            if torch.cuda.is_available():
                torch.cuda.reset_peak_memory_stats()
            local = QwenLoRAProvider("Qwen/Qwen3-1.7B", str(path), local_files_only=True)
            start = perf_counter()
            try:
                local._load()
            except Exception as exc:
                report["load_error_type"] = type(exc).__name__
                write_report(args.output, report)
                print("Local load failed; details sanitized, no fallback API call")
                return 2
            report["cold_load_ms"] = (perf_counter() - start) * 1000
            report["load_summary"] = local.load_summary
        for case in suite["cases"]:
            if source_hashes() != report["source_checksums"]:
                report["stopped"] = "runtime_changed_during_benchmark"
                write_report(args.output, report)
                return 3
            print(f"[{len(report['cases']) + 1}/{len(suite['cases'])}] {case['id']}", flush=True)
            report["cases"].append(evaluate_case(case, local, replay=replay.get(case["id"])))
            if local is not None and torch.cuda.is_available():
                report["peak_gpu_allocated_bytes"] = torch.cuda.max_memory_allocated()
                report["peak_gpu_reserved_bytes"] = torch.cuda.max_memory_reserved()
            report["summary"] = summary(report["cases"])
            write_report(args.output, report)
    print(json.dumps({s: report["summary"][s]["delta_exact"] for s in ("rule", "raw", "canonical", "effective")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
