"""No external requests: fake SDK and real SDK with local HTTP transport only."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ai2_tools as harness
import benchmark_ai2 as benchmark
import gemini_smoke_test as smoke
from common.schemas import UserRequest
from conversation import process_user_request
from conversation.providers import ProviderError
from conversation.providers.gemini_provider import GeminiProvider
from test_providers import wire_payload


@pytest.mark.parametrize("key,model,missing", [(None, "model", "GEMINI_API_KEY"),
    ("secret", None, "GEMINI_MODEL"), (" ", "model", "GEMINI_API_KEY"), ("secret", " ", "GEMINI_MODEL")])
def test_missing_gemini_config(key, model, missing):
    with pytest.raises(ProviderError, match=missing):
        GeminiProvider(api_key=key, model=model)


@pytest.mark.parametrize("outcome", ["success", "invalid", "api", "timeout"])
def test_actual_sdk_offline_transport(outcome, tmp_path):
    pytest.importorskip("google.genai")
    import httpx
    count = 0
    def handler(request):
        nonlocal count
        count += 1
        body = json.loads(request.content)
        assert "responseJsonSchema" in body["generationConfig"]
        if outcome == "timeout":
            raise httpx.ReadTimeout("secret-credential", request=request)
        if outcome == "api":
            return httpx.Response(503, json={"error": {"code": 503, "message": "secret-credential"}})
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [
            {"text": json.dumps(wire_payload()) if outcome == "success" else "invalid secret-credential"}]}}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 20, "totalTokenCount": 30}})
    config = harness.ConversationConfig(gemini_api_key="secret-credential", log_enabled=True,
                                        log_path=str(tmp_path / "log.jsonl"))
    provider = GeminiProvider(api_key="secret-credential", model="chosen-model")
    provider._client._api_client._httpx_client.close()
    provider._client._api_client._httpx_client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        result = process_user_request(UserRequest(session_id="sdk", message="ramen dưới 150k, nói chuyện lâu"),
                                      provider, config=config)
        assert count == 1
        assert result.state.hard_constraints["budget_max"] == 150000
        assert result.metadata.partial_result == (outcome != "success")
        assert "secret-credential" not in result.model_dump_json()
        assert "secret-credential" not in Path(config.log_path).read_text()
        if outcome == "invalid":
            assert result.metadata.llm_error == "invalid_output"
        if outcome == "success":
            assert result.metadata.usage == {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}
            assert json.loads(Path(config.log_path).read_text())["usage"]["total_tokens"] == 30
        # Rule request never invokes the already constructed SDK.
        rule = process_user_request(UserRequest(session_id="r", message=smoke.CASES[0]["message"]), provider)
        assert not rule.metadata.llm_called and count == 1
    finally:
        provider.close()


def test_smoke_dry_run_no_provider(monkeypatch, capsys):
    monkeypatch.setattr(smoke, "load_env", lambda: None)
    monkeypatch.setattr(smoke, "make_provider", lambda *a: pytest.fail("real provider constructed"))
    assert smoke.main(["--dry-run"]) == 0
    text = capsys.readouterr().out
    assert text.count("STATUS:\nDRY_RUN") == 8
    assert "GEMINI CALLED:\ntrue" not in text
    assert smoke.main(["--dry-run", "--case", "3"]) == 0
    assert capsys.readouterr().out.count("STATUS:") == 1


def test_benchmark_mock_limit_and_redaction(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(benchmark, "load_env", lambda: None)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "secret-credential")
    samples = [{**smoke.CASES[0], "id": str(i), "message": "ramen secret-credential"} for i in range(3)]
    dataset = tmp_path / "data.jsonl"
    dataset.write_text("\n".join(json.dumps(s) for s in samples))
    assert benchmark.main(["--limit", "2", "--dataset", str(dataset), "--output-dir", str(tmp_path)]) == 0
    result = next(tmp_path.glob("ai2_mock_*.json")).read_text(encoding="utf-8")
    assert "secret-credential" not in result + capsys.readouterr().out
    report = json.loads(result)
    assert report["provider"] == "mock" and report["number_prompts"] == 2
    assert len(report["cases"]) == 2
    assert not any(r["gemini_called"] for r in report["cases"])


@pytest.mark.parametrize("argv", [["--provider", "gemini"], ["--limit", "0"], ["--limit", "-1"]])
def test_benchmark_rejects_unsafe_args(argv):
    with pytest.raises(SystemExit) as error:
        benchmark.main(argv)
    assert error.value.code == 2


def test_metrics_and_subset():
    config = harness.ConversationConfig()
    record = harness.run_case(smoke.CASES[0], harness.make_provider("mock", config), config)
    assert record["status"] == "PASS"
    records = [json.loads(json.dumps(record)) for _ in range(20)]
    for i, row in enumerate(records):
        row["result"]["metadata"]["total_ms"] = i + 1
    records[0]["checks"][0]["correct"] = False
    records[0]["result"]["metadata"].update(llm_called=True, requires_llm=True,
        partial_result=True, llm_error="invalid_output")
    summary = harness.summarize(records)
    assert summary["correct"] == 19 and summary["accuracy_pct"] == 95
    assert summary["llm_count"] == 1 and summary["rule_only_count"] == 19
    assert summary["latency_ms"]["total"] == {"average": 10.5, "p50": 10, "p95": 19}
    assert summary["errors"]["validation_error"] == 1
    assert summary["errors"]["incorrect_deterministic_field"] == 1
    assert harness.summarize([])["accuracy_pct"] is None
    assert not harness.subset_checks({"x": None}, {})[0]["correct"]
    assert not harness.subset_checks(True, 1)[0]["correct"]


def test_dataset_valid_balanced_without_running_benchmark():
    rows = [json.loads(line) for line in (harness.ROOT / "benchmarks/ai2_vietnamese_prompts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == len({r["id"] for r in rows}) == 105
    categories = {r["category"] for r in rows}
    assert len(categories) == 15
    for category in categories:
        assert sum(r["category"] == category for r in rows) == 7
    for row in rows:
        harness.request_for(row)
        assert "expected" in row


def test_env_loading_preserves_exported_values(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_MODEL", "chosen")
    path = tmp_path / ".env"
    path.write_text('GEMINI_MODEL=other\nGEMINI_API_KEY="local-value"\n')
    harness.load_env(path)
    config = harness.ConversationConfig.from_env()
    assert config.gemini_model == "chosen" and config.gemini_api_key == "local-value"


def test_benchmark_explicit_gemini_limit_with_fake(monkeypatch, tmp_path):
    monkeypatch.setattr(benchmark, "load_env", lambda: None)
    provider = harness.make_provider("mock", harness.ConversationConfig())
    provider.name = "gemini"
    provider.close = lambda: None
    monkeypatch.setattr(benchmark, "make_provider", lambda *args: provider)
    dataset = tmp_path / "data.jsonl"
    dataset.write_text("\n".join(json.dumps({**smoke.CASES[1], "id": str(i)}) for i in range(5)))
    assert benchmark.main(["--provider", "gemini", "--limit", "2", "--dataset", str(dataset),
                           "--output-dir", str(tmp_path)]) == 0
    assert provider.call_count == 2


def test_usage_optional_resets_and_form_fallback():
    from types import SimpleNamespace
    from unittest.mock import Mock
    provider = GeminiProvider.__new__(GeminiProvider)
    provider.model = "fake"
    endpoint = Mock(side_effect=[SimpleNamespace(text=json.dumps(wire_payload()),
        usage_metadata=SimpleNamespace(prompt_token_count=10)),
        SimpleNamespace(text="invalid"), SimpleNamespace(text=json.dumps(wire_payload()),
        usage_metadata=SimpleNamespace(prompt_token_count="unknown", total_token_count=-1))])
    provider._client = SimpleNamespace(models=SimpleNamespace(generate_content=endpoint))
    request = UserRequest(session_id="usage", message="muốn quán riêng tư", form={"budget_max": 100000})
    first = process_user_request(request, provider)
    assert first.metadata.usage == {"input_tokens": 10}
    second = process_user_request(request, provider)
    assert second.metadata.usage == {} and second.metadata.partial_result
    assert second.state.hard_constraints["budget_max"] == 100000
    third = process_user_request(request, provider)
    assert third.metadata.usage == {} and not third.metadata.partial_result
    assert endpoint.call_count == 3


def test_dry_run_has_no_log_or_measured_metrics(tmp_path):
    config = harness.ConversationConfig(log_enabled=True, log_path=str(tmp_path / "log"))
    record = harness.run_case(smoke.CASES[1], None, config, dry_run=True)
    assert not Path(config.log_path).exists()
    assert record["would_call_gemini"] and not record["gemini_called"]
    assert not record["result"]["metadata"]["llm_called"]
    assert harness.summarize([record])["total_requests"] == 0


@pytest.fixture
def benchmark_samples():
    return benchmark.load_dataset(harness.ROOT / "benchmarks/ai2_vietnamese_prompts.jsonl")


@pytest.mark.parametrize("options,expected_count,cap", [
    ({"one_per_category": True}, 15, 1),
    ({"per_category": 2}, 30, 2),
    ({"categories": ["semantic", "feedback"]}, 14, 7),
    ({"categories": ["semantic", "feedback"], "per_category": 2}, 4, 2),
    ({"per_category": 20}, 105, 7),
])
def test_benchmark_category_selection(benchmark_samples, options, expected_count, cap):
    selected = benchmark.select_samples(benchmark_samples, **options)
    names = list(dict.fromkeys(row["category"] for row in benchmark_samples))
    expected_names = [name for name in names if name in options.get("categories", names)]
    assert len(selected) == expected_count
    assert list(dict.fromkeys(row["category"] for row in selected)) == expected_names
    for name in expected_names:
        assert [row for row in selected if row["category"] == name] == [
            row for row in benchmark_samples if row["category"] == name][:cap]


def test_benchmark_limit_after_selection(benchmark_samples):
    selected = benchmark.select_samples(benchmark_samples, categories=["feedback", "semantic"],
                                        per_category=3, limit=4)
    assert [row["category"] for row in selected] == ["semantic"] * 3 + ["feedback"]
    selected = benchmark.select_samples(benchmark_samples, one_per_category=True, limit=4)
    assert [row["category"] for row in selected] == ["simple_food", "budget", "distance", "combined"]


@pytest.mark.parametrize("argv,message", [
    (["--one-per-category", "--per-category", "3"],
     "use either --one-per-category or --per-category, not both."),
    (["--categories", "nonexistent"], "Unknown categories: nonexistent. Valid categories:"),
    (["--per-category", "0"], "count must be positive"),
    (["--per-category", "-2"], "count must be positive"),
    (["--provider", "gemini", "--categories", "semantic", "feedback"], "requires an explicit"),
    (["--provider", "gemini", "--dry-run"], "requires an explicit"),
])
def test_benchmark_selection_errors_before_provider(monkeypatch, capsys, argv, message):
    monkeypatch.setattr(benchmark, "make_provider", lambda *a: pytest.fail("provider constructed"))
    with pytest.raises(SystemExit) as error:
        benchmark.main(argv)
    assert error.value.code == 2
    stderr = capsys.readouterr().err
    assert message in stderr
    if "nonexistent" in argv:
        assert "simple_food" in stderr and "typo_slang" in stderr


@pytest.mark.parametrize("provider", ["mock", "gemini"])
def test_list_categories_without_config_or_provider(monkeypatch, capsys, tmp_path, provider):
    monkeypatch.setattr(benchmark, "load_env", lambda: pytest.fail("configuration loaded"))
    monkeypatch.setattr(benchmark, "make_provider", lambda *a: pytest.fail("provider constructed"))
    monkeypatch.setattr(benchmark, "run_case", lambda *a: pytest.fail("benchmark executed"))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    output = tmp_path / "unused"
    assert benchmark.main(["--provider", provider, "--list-categories", "--output-dir", str(output)]) == 0
    text = capsys.readouterr().out
    assert text.startswith("simple_food: 7\nbudget: 7\n")
    assert "typo_slang: 7\n\nTOTAL:\n15 categories\n105 samples" in text
    assert len([line for line in text.splitlines() if line.endswith(": 7")]) == 15
    assert not output.exists()


@pytest.mark.parametrize("provider_name,options,count", [
    ("mock", ["--one-per-category"], 15),
    ("gemini", ["--one-per-category"], 15),
    ("gemini", ["--categories", "semantic", "feedback", "--per-category", "2"], 4),
    ("gemini", ["--per-category", "2"], 30),
])
def test_benchmark_selection_report_offline(monkeypatch, tmp_path, capsys, provider_name, options, count):
    monkeypatch.setattr(benchmark, "load_env", lambda: None)
    monkeypatch.setenv("CONVERSATION_LOG_ENABLED", "false")
    provider = harness.make_provider("mock", harness.ConversationConfig())
    closed = []
    provider.close = lambda: closed.append(True)
    monkeypatch.setattr(benchmark, "make_provider", lambda *a: provider)
    assert benchmark.main(["--provider", provider_name, *options, "--output-dir", str(tmp_path)]) == 0
    report = json.loads(next(tmp_path.glob("ai2_*.json")).read_text(encoding="utf-8"))
    names = list(dict.fromkeys(row["category"] for row in report["cases"]))
    assert report["number_prompts"] == len(report["cases"]) == count
    assert report["provider"] == provider_name
    assert "model" in report
    assert report["selection"] == {"categories": names, "one_per_category": "--one-per-category" in options,
                                    "per_category": 2 if "--per-category" in options else None, "limit": None}
    assert report["summary"]["categories_tested"] == len(names)
    assert report["summary"]["category_names"] == names
    assert not any(row["gemini_called"] for row in report["cases"])
    if provider_name == "gemini":
        assert closed == [True]
        assert (f"You are about to process {count} benchmark samples across {len(names)} categories. "
                "Gemini calls may consume quota.") in capsys.readouterr().out
