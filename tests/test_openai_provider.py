"""OpenAI integration coverage: fake SDK only, with the suite network guard enabled."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from common.schemas import UserRequest
from conversation import process_user_request
from conversation.config import ConversationConfig, create_provider
from conversation.interactive import cli
from conversation.interactive.session import InteractiveSession
from conversation.providers import ProviderError
from conversation.providers.openai_provider import OpenAIProvider
from conversation.providers.structured import StructuredPreferenceUpdate
from test_providers import wire_payload

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ai2_tools
import benchmark_ai2
import openai_smoke_test


@pytest.fixture
def sdk(monkeypatch):
    payload = wire_payload()
    payload["set_values"] = {"food": ["cơm tấm"], "cuisine": ["Nhật"], "location": None}
    payload["add_hard_constraints"] = [{"key": "parking", "value": True},
                                       {"key": "custom_string", "value": "yes"},
                                       {"key": "custom_number", "value": 3.5}]
    payload["add_negative_preferences"] = ["đồ cay"]
    payload["relative_updates"] = {"budget": None, "distance": None}
    endpoint = Mock(return_value=SimpleNamespace(
        output_parsed=StructuredPreferenceUpdate.model_validate(payload),
        usage=SimpleNamespace(input_tokens=12, output_tokens=34, total_tokens=46)))
    client = SimpleNamespace(responses=SimpleNamespace(parse=endpoint), close=Mock())
    constructor = Mock(return_value=client)
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=constructor))
    return constructor, endpoint


@pytest.mark.parametrize("model", [None, "", "  ", "custom-model"])
def test_factory_default_and_configured_model(sdk, monkeypatch, model):
    if model is not None:
        monkeypatch.setenv("OPENAI_MODEL", model)
    monkeypatch.setenv("OPENAI_API_KEY", "secret-key")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    config = ConversationConfig.from_env()
    provider = create_provider(config)
    assert isinstance(provider, OpenAIProvider)
    assert provider.model == ("custom-model" if model == "custom-model" else "gpt-5.6-luna")
    assert sdk[0].call_args.kwargs == {"api_key": "secret-key", "max_retries": 0, "timeout": 30.0}
    provider.close()
    sdk[0].return_value.close.assert_called_once()


def test_rule_gate_context_normalization_and_usage(sdk):
    config = ConversationConfig(llm_provider="openai", openai_api_key="secret-key")
    rule = process_user_request(UserRequest(session_id="S", message="Trong vòng 2km thôi"), config=config)
    assert not rule.metadata.llm_called
    sdk[0].assert_not_called()
    request = UserRequest(session_id="S", message="Muốn ăn cơm tấm dưới 50k, gần gần thôi",
                          current_state=rule.state, previous_results=[{"rank": 1, "restaurant_id": "R1"}])
    result = process_user_request(request, config=config)
    sdk[1].assert_called_once()
    context = json.loads(sdk[1].call_args.kwargs["input"])
    assert context["message"] == request.message
    assert context["current_state"] == rule.state.model_dump()
    assert context["previous_results"] == [r.model_dump() for r in request.previous_results]
    assert context["rule_update"]["add_hard_constraints"]["budget_max"] == 50000
    assert result.state.food == ["cơm tấm"]
    assert result.state.cuisine == ["japanese"]
    assert result.state.negative_preferences == ["spicy"]
    assert "parking" not in result.state.hard_constraints  # v0.2: no explicit parking evidence.
    assert result.state.hard_constraints["custom_string"] == "yes"
    assert result.state.hard_constraints["custom_number"] == 3.5
    assert result.metadata.usage == {"input_tokens": 12, "output_tokens": 34, "total_tokens": 46}
    assert result.metadata.llm_ms >= 0


@pytest.mark.parametrize("status,code", [(429, "rate_limit"), (401, "authentication_error"),
                                         (403, "authentication_error"), (503, "provider_error"),
                                         (None, "timeout")])
def test_failure_session_and_secret_redaction(sdk, monkeypatch, tmp_path, capsys, caplog, status, code):
    error = RuntimeError("Authorization: secret-key") if status else TimeoutError("secret-key")
    error.status_code = status
    sdk[1].side_effect = error
    monkeypatch.setenv("OPENAI_API_KEY", "secret-key")
    session = InteractiveSession(provider="openai", directory=tmp_path)
    record = session.process("ramen dưới 150k, nói chuyện lâu")
    sdk[1].assert_called_once()
    assert record["provider"] == "openai"
    assert record["metadata"]["llm_error"] == code
    assert record["metadata"]["parser_used"] == "rule_fallback"
    assert record["metadata"]["partial_result"]
    assert not record["metadata"]["external_llm_disabled"]
    assert record["new_state"]["hard_constraints"]["budget_max"] == 150000
    assert not session.process("Trong vòng 2km thôi")["llm_called"]
    config = ConversationConfig(openai_api_key="secret-key", log_enabled=True, log_path=str(tmp_path / "events.jsonl"))
    process_user_request(UserRequest(session_id="S", message="unknown"),
                         OpenAIProvider(api_key="secret-key"), config=config)
    printed = []
    commands = iter(["/state", "/exit"])
    cli.run_repl(session, read=lambda _: next(commands), write=printed.append)
    text = "".join(p.read_text(encoding="utf-8") for p in tmp_path.glob("*.jsonl"))
    assert "secret-key" not in text + json.dumps(record) + capsys.readouterr().out + caplog.text + "".join(printed)


def test_initialization_error_is_sanitized(sdk):
    sdk[0].side_effect = RuntimeError("secret-key")
    with pytest.raises(ProviderError) as error:
        OpenAIProvider(api_key="secret-key")
    assert "secret-key" not in str(error.value)


def test_usage_missing_invalid_and_reset(sdk):
    provider = OpenAIProvider(api_key="unused")
    provider.parse_preference(message="unknown", current_state=None, previous_results=[])
    sdk[1].return_value.usage = SimpleNamespace(input_tokens=True, output_tokens=-1, total_tokens=None)
    provider.parse_preference(message="unknown", current_state=None, previous_results=[])
    assert provider.last_usage == {}
    del sdk[1].return_value.usage
    provider.parse_preference(message="unknown", current_state=None, previous_results=[])
    assert provider.last_usage == {}


def test_interactive_switch_and_cli(sdk, monkeypatch, tmp_path):
    session = InteractiveSession(provider="rule", directory=tmp_path)
    output = []
    commands = iter(["/provider openai", "Trong vòng 2km thôi", "/exit"])
    cli.run_repl(session, read=lambda _: next(commands), write=output.append)
    assert "Provider: openai" in output
    assert "OpenAI mode enabled. Messages that require LLM may consume API quota." in output
    assert session.provider == "openai"
    sdk[0].assert_not_called()
    observed = []
    monkeypatch.setattr(cli, "run_repl", lambda session: observed.append(session.provider))
    cli.main(["--provider", "openai", "--no-save"])
    assert observed == ["openai"]


@pytest.mark.parametrize("extra", [[], ["--dry-run"], ["--categories", "semantic"]])
def test_benchmark_openai_requires_bound(extra):
    with pytest.raises(SystemExit) as error:
        benchmark_ai2.main(["--provider", "openai", *extra])
    assert error.value.code == 2


def test_benchmark_and_smoke_offline(sdk, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(benchmark_ai2, "load_env", lambda: None)
    monkeypatch.setattr(openai_smoke_test, "load_env", lambda: None)
    assert benchmark_ai2.main(["--provider", "openai", "--one-per-category", "--dry-run",
                               "--output-dir", str(tmp_path)]) == 0
    report = json.loads(next(tmp_path.glob("ai2_openai_*.json")).read_text(encoding="utf-8"))
    assert report["provider"] == "openai" and report["model"] == "gpt-5.6-luna"
    assert all(r["planned_request"]["model"] == "gpt-5.6-luna" for r in report["cases"])
    assert openai_smoke_test.main(["--dry-run", "--case", "1"]) == 0
    sdk[0].assert_not_called()
    monkeypatch.setenv("OPENAI_API_KEY", "secret-key")
    sdk[1].return_value.output_parsed.set_values.food = ["ramen"]
    assert openai_smoke_test.main(["--case", "2"]) == 0
    assert "Explicit smoke run: may consume OpenAI API quota." in capsys.readouterr().out
    assert isinstance(ai2_tools.make_provider("openai", ConversationConfig(openai_api_key="secret-key")), OpenAIProvider)


@pytest.mark.parametrize("outcome,code", [("success", None), ("invalid", "invalid_output"),
    ("refusal", "invalid_output"), ("timeout", "timeout"),
    ("429", "rate_limit"), ("401", "authentication_error"), ("503", "provider_error")])
def test_official_sdk_local_transport(outcome, code, monkeypatch):
    openai = pytest.importorskip("openai")
    import httpx

    count = 0
    payload = wire_payload()
    payload["add_hard_constraints"] = [{"key": "parking", "value": True}]

    def handler(request):
        nonlocal count
        count += 1
        body = json.loads(request.content)
        assert request.url.path == "/v1/responses"
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["text"]["format"]["strict"] is True
        assert body["model"] == "gpt-5.6-luna"
        if outcome == "timeout":
            raise httpx.ReadTimeout("secret-key", request=request)
        if outcome.isdigit():
            return httpx.Response(int(outcome), json={"error": {"message": "secret-key"}})
        content = ({"type": "refusal", "refusal": "cannot comply"} if outcome == "refusal" else
                   {"type": "output_text", "text": json.dumps(payload) if outcome == "success" else "{}",
                    "annotations": []})
        return httpx.Response(200, json={
            "id": "resp_test", "object": "response", "created_at": 1, "status": "completed",
            "model": "gpt-5.6-luna", "output": [{"id": "msg_test", "type": "message",
                "status": "completed", "role": "assistant", "content": [content]}],
            "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}})

    constructor = openai.OpenAI
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: constructor(
        **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handler))))
    provider = OpenAIProvider(api_key="secret-key")
    try:
        result = process_user_request(UserRequest(session_id="S", message="ramen dưới 150k, nói chuyện lâu"), provider)
        assert count == 1
        assert result.metadata.llm_error == code
        assert result.metadata.partial_result == (outcome != "success")
        assert result.state.hard_constraints["budget_max"] == 150000
        assert "secret-key" not in result.model_dump_json()
        if outcome == "success":
            assert "parking" not in result.state.hard_constraints  # Ignore invented parking.
            assert result.metadata.usage == {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}
    finally:
        provider.close()
