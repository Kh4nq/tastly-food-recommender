"""Shared offline-safe harness; expectations are never used as mock answers."""
from __future__ import annotations

from dataclasses import replace
import json
import math
from pathlib import Path
from statistics import mean
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.schemas import PreferenceUpdate, UserRequest
from conversation import process_user_request
from conversation.config import ConversationConfig, create_provider
from conversation.environment import load_env
from conversation.conversation_logger import _redact
from conversation.prompts import SYSTEM_PROMPT, build_context
from conversation.providers import MockProvider


def safe(value, config):
    return _redact(value, (config.gemini_api_key, config.openai_api_key))


def dump(value, config):
    return json.dumps(safe(value, config), ensure_ascii=False, indent=2, allow_nan=False)


def make_provider(name, config):
    if name != "mock":
        return create_provider(replace(config, llm_provider=name))
    # Deliberately empty inference: measures harness/rules, not semantic quality.
    return MockProvider(callback=lambda **kwargs: PreferenceUpdate())


def request_for(sample):
    state = sample.get("current_state") or None
    session = state.get("session_id", sample["id"]) if state else sample["id"]
    return UserRequest(session_id=session, message=sample["message"],
                       current_state={**state, "session_id": session} if state else None,
                       previous_results=sample.get("previous_results", []))


def subset_checks(expected, actual, path=""):
    """Dict subset, list membership/subset, scalar equality; absent differs from null."""
    checks = []
    if isinstance(expected, dict):
        if not expected and path:
            return [{"field": path, "correct": actual == {}}]
        for key, value in expected.items():
            label = f"{path}.{key}".strip(".")
            if not isinstance(actual, dict) or key not in actual:
                checks.append({"field": label, "correct": False})
            else:
                checks.extend(subset_checks(value, actual[key], label))
    elif isinstance(expected, list):
        for index, value in enumerate(expected):
            correct = isinstance(actual, list) and any(
                all(c["correct"] for c in subset_checks(value, item, path)) for item in actual)
            checks.append({"field": f"{path}[{index}]", "correct": correct})
        if not expected:
            checks.append({"field": path, "correct": actual == []})
    else:
        checks.append({"field": path, "correct": type(expected) is type(actual) and expected == actual
                       or type(expected) in (int, float) and type(actual) in (int, float) and expected == actual})
    return checks


def evaluate(sample, result):
    state = result["state"]
    view = {**state, "relative_updates": result["preference_update"]["relative_updates"],
            "update": result["preference_update"], "metadata": result["metadata"]}
    checks = subset_checks(sample.get("expected", {}), view)
    for path in sample.get("absent", []):
        node = view
        present = True
        for key in path.split("."):
            if not isinstance(node, dict) or key not in node:
                present = False
                break
            node = node[key]
        checks.append({"field": path + " (absent)", "correct": not present})
    failed = any(not check["correct"] for check in checks)
    status = ("FAIL" if failed or result["metadata"]["llm_error"] else
              "REVIEW" if sample.get("review") or not checks or result["metadata"]["partial_result"] else "PASS")
    return checks, status


def run_case(sample, provider, config, dry_run=False, *, provider_name="gemini"):
    request = request_for(sample)
    # Passing an explicit offline provider prevents environment-driven API use.
    from dataclasses import replace
    result = process_user_request(request, MockProvider(callback=lambda **kw: PreferenceUpdate())
                                  if dry_run else provider,
                                  config=replace(config, log_enabled=False, local_slm_enabled=False) if dry_run else config)
    payload = result.model_dump(mode="json")
    checks, status = evaluate(sample, payload)
    record = {"id": sample["id"], "category": sample["category"], "message": sample["message"],
              "result": payload, "checks": checks, "status": "DRY_RUN" if dry_run else status,
              "review": sample.get("review"), "dry_run": dry_run,
              "gemini_called": not dry_run and payload["metadata"]["provider"] == "gemini"
              and payload["metadata"]["llm_called"]}
    record["openai_called"] = (not dry_run and payload["metadata"]["provider"] == "openai"
                               and payload["metadata"]["llm_called"])
    if dry_run:
        record["would_call_" + provider_name] = result.metadata.requires_llm
        record["planned_request"] = {"model": getattr(config, provider_name + "_model", None), "system_instruction": SYSTEM_PROMPT,
            "response_schema": "StructuredPreferenceUpdate", "context": json.loads(build_context(
                message=request.message or "", current_state=request.current_state,
                previous_results=request.previous_results, rule_update=result.rule_result.update))}
        # Offline simulation timings/LLM invocation are not real measurements.
        payload["metadata"].update(llm_called=False, llm_ms=0, provider=None)
    return safe(record, config)


def summarize(records):
    measured = [r for r in records if not r["dry_run"]]
    count = len(measured)
    metas = [r["result"]["metadata"] for r in measured]
    llm = sum(m["llm_called"] for m in metas)
    rule = sum(not m["requires_llm"] for m in metas)
    checks = [c for r in measured for c in r["checks"]]
    evaluated = [r for r in measured if r["checks"]]
    correct = sum(all(c["correct"] for c in r["checks"]) for r in evaluated)
    def ratio(a, b):
        return 100 * a / b if b else None
    def latency(key, items):
        values = sorted(m[key] for m in items)
        return {"average": mean(values) if values else None,
                "p50": values[math.ceil(len(values) * .5) - 1] if values else None,
                "p95": values[math.ceil(len(values) * .95) - 1] if len(values) >= 20 else None}
    categories = {}
    category_names = list(dict.fromkeys(r["category"] for r in measured))
    for category in sorted({r["category"] for r in measured}):
        rows = [r for r in evaluated if r["category"] == category]
        n = sum(all(c["correct"] for c in r["checks"]) for r in rows)
        categories[category] = {"correct": n, "evaluated": len(rows), "accuracy_pct": ratio(n, len(rows)),
                               "review": sum(r["status"] == "REVIEW" for r in measured if r["category"] == category)}
    return {"total_requests": count, "dry_run_count": len(records) - count,
            "categories_tested": len(category_names), "category_names": category_names,
            "rule_only_count": rule, "llm_count": llm, "rule_coverage_pct": ratio(rule, count),
            "llm_call_rate_pct": ratio(llm, count), "correct": correct, "evaluated": len(evaluated),
            "accuracy_pct": ratio(correct, len(evaluated)), "field_correct": sum(c["correct"] for c in checks),
            "field_total": len(checks), "field_accuracy_pct": ratio(sum(c["correct"] for c in checks), len(checks)),
            "review_count": sum(r["status"] == "REVIEW" for r in measured),
            "latency_ms": {"rule": latency("rule_parse_ms", metas),
                           "llm": latency("llm_ms", [m for m in metas if m["llm_called"]]),
                           "total": latency("total_ms", metas)},
            "errors": {"api_error": sum(m["llm_error"] in ("provider_error", "timeout", "provider_unavailable", "rate_limit", "authentication_error") for m in metas),
                       "validation_error": sum(m["llm_error"] == "invalid_output" for m in metas),
                       "partial_result": sum(m["partial_result"] for m in metas),
                       "incorrect_deterministic_field": sum(not c["correct"] for c in checks)},
            "usage": {key: sum(m["usage"].get(key, 0) for m in metas)
                      for key in ("input_tokens", "output_tokens", "total_tokens")
                      if any(key in m["usage"] for m in metas)}, "categories": categories}
