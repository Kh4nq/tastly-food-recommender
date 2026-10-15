"""Prepare bounded Gemini/OpenRouter evaluation. Default dry-run; mock is offline.

Live is an explicit future user action requiring BOTH --live and
--confirm-external-calls. No provider is invoked automatically from env settings.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext, contextmanager
from dataclasses import replace
import json
from pathlib import Path
import sys
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from conversation.config import ConversationConfig, create_provider
from conversation.conversation_logger import _redact
from conversation.environment import load_env
from conversation.providers.base import ProviderError
from conversation.providers.gemini_provider import GeminiProvider
from conversation.providers.openrouter_provider import OpenRouterProvider
from conversation.service import process_user_request
from conversation.slm.base import SLMParseResult
from scripts.ai2_benchmark_budget import BudgetLedger, BudgetExceeded
from scripts.ai2_benchmark_metrics import score, raw_stages
from scripts.benchmark_ai2_freeze import DEFAULT_SUITE, sha256, source_hashes, request_for, input_for, offline_network, forbid_sealed


def empty_wire():
    # Fixed mock transport fixture, NEVER an expected benchmark label.
    return {"set_values": {"food": None, "cuisine": None, "location": None},
            "add_hard_constraints": [], "add_soft_preferences": [], "add_semantic_preferences": [],
            "add_negative_preferences": [], "context_updates": [], "remove_preferences": [],
            "references": [], "relative_updates": {"budget": None, "distance": None}}


class BoundedProvider:
    def __init__(self, inner, ledger):
        self.inner, self.ledger, self.name = inner, ledger, inner.name
        self.last_usage, self.last_cost_usd, self.last_attempts = {}, None, 0
        self.blocked = False
        self.last_schema_valid = False

    def parse_preference(self, **kwargs):
        self.last_usage, self.last_cost_usd, self.last_attempts = {}, None, 0
        self.last_schema_valid = False
        try:
            self.ledger.admit()
        except BudgetExceeded:
            self.blocked = True
            raise
        valid = False
        try:
            result = self.inner.parse_preference(**kwargs)
            valid = True
            self.last_schema_valid = True
            return result
        finally:
            self.last_usage = dict(getattr(self.inner, "last_usage", {}))
            self.last_cost_usd = getattr(self.inner, "last_cost_usd", None)
            self.last_attempts = getattr(self.inner, "last_attempts", 1)
            self.ledger.settle(self.last_cost_usd, valid=valid)


def mock_provider(name, model):
    if name == "gemini":
        provider = object.__new__(GeminiProvider)
        provider.model, provider.last_usage = model, {}
        def generate(**kwargs):
            provider.benchmark_wire = empty_wire()
            provider.benchmark_request = kwargs
            return SimpleNamespace(text=json.dumps(provider.benchmark_wire), usage_metadata=SimpleNamespace(
                prompt_token_count=12, candidates_token_count=7, total_token_count=19))
        provider._client = SimpleNamespace(models=SimpleNamespace(generate_content=generate), close=lambda: None)
        return provider, nullcontext()
    provider = OpenRouterProvider(api_key="benchmark-mock-credential", enabled=True, model=model,
                                  structured_output=True, max_retries=0)
    def send(request, **kwargs):
        provider.benchmark_request = json.loads(request.data)
        provider.benchmark_wire = empty_wire()
        data = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(provider.benchmark_wire)}}],
                           "usage": {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19, "cost": .0001}}).encode()
        return nullcontext(SimpleNamespace(read=lambda _: data))
    return provider, patch("conversation.providers.openrouter_provider.urlopen", side_effect=send)


def bounded_gemini_client(provider, max_tokens):
    """Benchmark-instance output cap and wire tap; production code unchanged."""
    client = provider._client
    def generate(**kwargs):
        kwargs["config"] = {**kwargs["config"], "max_output_tokens": max_tokens, "temperature": 0, "candidate_count": 1}
        response = client.models.generate_content(**kwargs)
        try:
            provider.benchmark_wire = json.loads(response.text)
        except (ValueError, TypeError, AttributeError, RecursionError):
            provider.benchmark_wire = None
        return response
    provider._client = SimpleNamespace(models=SimpleNamespace(generate_content=generate), close=client.close)


def tap_openrouter(provider):
    """Capture returned JSON through the existing transport, no extra request."""
    import conversation.providers.openrouter_provider as wire
    original_send = wire.urlopen
    @contextmanager
    def send(request, **kwargs):
        with original_send(request, **kwargs) as response:
            def read(limit):
                body = response.read(limit)
                try:
                    outer = json.loads(body)
                    provider.benchmark_wire = json.loads(outer["choices"][0]["message"]["content"])
                except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError):
                    provider.benchmark_wire = None
                return body
            yield SimpleNamespace(read=read)
    return patch.object(wire, "urlopen", side_effect=send)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--provider", choices=["gemini", "qwen32", "deepseek32", "openrouter"], required=True)
    parser.add_argument("--experiment-config", type=Path, help="Isolated OpenRouter benchmark configuration")
    parser.add_argument("--model-profile", help="Profile name from the experimental configuration")
    parser.add_argument("--case-set", choices=["compatibility1", "smoke8", "full47"], help="Frozen eval48 subset")
    parser.add_argument("--resume-from", type=Path, help="Read-only source report for experimental full47 resume")
    parser.add_argument("--resume-config", type=Path, help="Original config file matching the source report checksum")
    parser.add_argument("--mode", choices=["independent", "fallback"], default="independent")
    parser.add_argument("--local-report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--confirm-external-calls", action="store_true")
    parser.add_argument("--max-calls", type=int, default=3)
    parser.add_argument("--budget-usd", default="1")
    parser.add_argument("--reserve-usd", default="0.10")
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--case-id", action="append", help="Select frozen case IDs before any provider call")
    args = parser.parse_args(argv)
    if args.provider == "openrouter":
        from scripts.ai2_openrouter_experiment import run_experiment
        return run_experiment(args, parser)
    if args.experiment_config or args.model_profile or args.case_set or args.resume_from or args.resume_config:
        parser.error("Experimental options require --provider openrouter")
    args.max_tokens = 1024 if args.max_tokens is None else args.max_tokens
    if args.output.exists():
        parser.error("Do not overwrite provider reports")
    if args.live and (args.mock or not args.confirm_external_calls):
        parser.error("Live requires separate confirmation and cannot combine with mock")
    if not 1 <= args.max_tokens <= 4096:
        parser.error("max-tokens must be 1..4096")
    if args.mode == "fallback" and not args.local_report:
        parser.error("Fallback requires a completed checksummed local report")
    ledger = BudgetLedger(args.max_calls, args.budget_usd, args.reserve_usd)
    sys.addaudithook(forbid_sealed)
    load_env()
    original = ConversationConfig.from_env()
    provider_name = "gemini" if args.provider == "gemini" else "openrouter"
    model = original.gemini_model if provider_name == "gemini" else "qwen/qwen3-32b" if args.provider == "qwen32" else "deepseek/deepseek-v3.2"
    if provider_name == "gemini" and not model:
        parser.error("GEMINI_MODEL must be explicit in runtime environment")
    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    report = {"execution": "live" if args.live else "mock" if args.mock else "dry-run", "mode": args.mode,
              "provider": provider_name, "model": model, "suite_sha256": sha256(args.suite),
              "quality_metrics_are_real": bool(args.live), "independent_gold_count": 0,
              "external_api_calls": 0, "benchmark_retries": 0, "timeout_seconds": 30,
              "source_checksums": source_hashes(),
              "output_limit": args.max_tokens, "output_schema": "StructuredPreferenceUpdate -> PreferenceUpdate",
              "budget_measurement": "synthetic simulation" if args.mock else "live reservations/returned usage" if args.live else "plan only",
              "budget": ledger.report(), "cases": []}
    previous = {}
    if args.local_report:
        data = json.loads(args.local_report.read_text(encoding="utf-8"))
        if data["suite_sha256"] != report["suite_sha256"] or len(data["cases"]) != len(suite["cases"]):
            parser.error("Local replay report is incomplete or from another frozen suite")
        if data["source_checksums"] != report["source_checksums"]:
            parser.error("Local report belongs to a different runtime; do not silently compare changed guards")
        previous = {r["id"]: r for r in data["cases"]}
        report["local_report_sha256"] = sha256(args.local_report)
    if args.case_id:
        selected_ids = set(args.case_id)
        if not selected_ids <= {c["id"] for c in suite["cases"]}:
            parser.error("Unknown frozen case ID")
        suite = {**suite, "cases": [c for c in suite["cases"] if c["id"] in selected_ids]}
    report["selected_case_ids"] = [c["id"] for c in suite["cases"]]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    secrets = (original.gemini_api_key, original.openrouter_api_key, original.openai_api_key, "benchmark-mock-credential")
    def save():
        args.output.write_text(json.dumps(_redact(report, secrets), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if not args.mock and not args.live:
        report["planned"] = [{"id": case["id"], "would_call_provider": args.mode == "independent" or bool(
                previous[case["id"]]["effective"]["metadata"]["requires_llm"] and
                previous[case["id"]]["effective"]["metadata"]["slm_fallback"])} for case in suite["cases"]]
        save()
        print("DRY RUN: runtime model read, no provider client/API call, budget configured")
        return 0
    if args.mock:
        inner, transport = mock_provider(provider_name, model)
        # Exercise the same benchmark-instance output cap in contract tests.
        if provider_name == "gemini":
            bounded_gemini_client(inner, args.max_tokens)
        else:
            inner.max_tokens = args.max_tokens
    else:
        # A one-off benchmark instance; no environment flag/default is rewritten.
        config = replace(original, llm_provider=provider_name, openrouter_enabled=provider_name == "openrouter",
            openrouter_model=model, openrouter_max_retries=0, openrouter_timeout=30,
            openrouter_max_tokens=args.max_tokens, openrouter_structured_output=True)
        inner, transport = create_provider(config), nullcontext()
        if provider_name == "gemini":
            bounded_gemini_client(inner, args.max_tokens)
        else:
            transport = tap_openrouter(inner)
    provider = BoundedProvider(inner, ledger)
    network = nullcontext() if args.live else offline_network()
    with network, transport:
        for case in suite["cases"]:
            before = ledger.calls
            start = perf_counter()
            request = request_for(case)
            inp = input_for(request, ConversationConfig())
            record = {"id": case["id"], "category": case["category"], "called": False, "error": None}
            valid = False
            if args.mode == "independent":
                try:
                    delta = provider.parse_preference(message=inp.message, current_state=inp.current_state,
                        previous_results=inp.previous_results, rule_update=inp.rule_result.update)
                    valid = True
                    record["domain_delta"] = delta.model_dump(mode="json")
                    record["scores"] = raw_stages(case, delta) if args.live else None
                except BudgetExceeded:
                    report["stopped"] = "call_or_budget_limit"
                    break
                except ProviderError as exc:
                    record["error"] = exc.code
                except Exception as exc:
                    # Audit unexpected adapter failures without leaking error
                    # bodies/keys; admission already reserved their possible bill.
                    record["error"] = "unexpected_provider_error"
                    record["error_type"] = type(exc).__name__
            else:
                raw = previous[case["id"]]["slm_result"]
                local = SimpleNamespace(parse=lambda _, raw=raw: SLMParseResult.model_validate(raw))
                effective = process_user_request(request, provider, config=ConversationConfig(local_slm_enabled=True,
                    llm_provider="none", log_enabled=False), slm_provider=local)
                if provider.blocked:
                    report["stopped"] = "call_or_budget_limit"
                    break
                valid = ledger.calls > before and not effective.metadata.llm_error
                record["effective"] = effective.model_dump(mode="json")
                record["scores"] = score(case, effective.preference_update, effective.state) if args.live else None
                record["error"] = effective.metadata.llm_error
            record["called"] = ledger.calls > before
            record["schema_response_valid"] = provider.last_schema_valid if record["called"] else None
            record["pipeline_accepted_response"] = valid if record["called"] and args.mode == "fallback" else None
            record["response_ms" if args.live else "mock_execution_ms"] = (perf_counter() - start) * 1000
            record["usage"] = provider.last_usage if record["called"] else {}
            record["actual_cost_usd"] = provider.last_cost_usd if args.live and record["called"] else None
            record["synthetic_mock_cost_usd"] = provider.last_cost_usd if args.mock and record["called"] else None
            record["wire_response"] = getattr(inner, "benchmark_wire", None) if record["called"] else None
            record["attempts"] = provider.last_attempts if record["called"] else 0
            report["cases"].append(record)
            report["external_api_calls"] = ledger.calls if args.live else 0
            report["budget"] = ledger.report()
            save()
    inner.close()
    report["budget"] = ledger.report()
    called = [c for c in report["cases"] if c["called"]]
    valid_count = sum(c["schema_response_valid"] is True for c in called)
    known_cost = sum(c["actual_cost_usd"] or 0 for c in called)
    all_costs_known = bool(args.live and called and all(c["actual_cost_usd"] is not None for c in called))
    report["run_summary"] = {"provider_calls": len(called), "schema_valid_responses": valid_count,
        "pipeline_accepted_responses": sum(c["pipeline_accepted_response"] is True for c in called),
        "actual_cost_usd": known_cost if all_costs_known else None,
        "actual_cost_per_schema_valid_response_usd": known_cost / valid_count if all_costs_known and valid_count else None,
        "reserved_estimate_usd": str(ledger.reserve * len(called))}
    save()
    print(json.dumps({"execution": report["execution"], "attempts": ledger.calls, "external_api_calls": report["external_api_calls"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
