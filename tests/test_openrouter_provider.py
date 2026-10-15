"""OpenRouter tests use fake HTTP; no credentials, paid calls or SDK required."""
from contextlib import nullcontext
import json
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

from common.schemas import UserRequest
from conversation.config import ConversationConfig, create_provider
from conversation.providers.base import ProviderError
from conversation.providers.openrouter_provider import OpenRouterProvider
import conversation.providers.openrouter_provider as wire
from conversation.service import process_user_request


def output():
    return {"set_values": {"food": None, "cuisine": None, "location": None},
            "add_hard_constraints": [], "add_soft_preferences": [],
            "add_semantic_preferences": ["view đẹp"], "add_negative_preferences": [],
            "context_updates": [], "remove_preferences": [], "references": [],
            "relative_updates": {"budget": None, "distance": None}}


def response(content=None, *, usage=None, finish="stop"):
    body = json.dumps({"choices": [{"finish_reason": finish,
        "message": {"content": json.dumps(content if content is not None else output())}}],
        "usage": usage or {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19, "cost": .0004}}).encode()
    return nullcontext(SimpleNamespace(read=lambda _: body))


def call(provider):
    return provider.parse_preference(message="view đẹp", current_state=None, previous_results=[])


def provider(**kwargs):
    return OpenRouterProvider(api_key="mock-only-secret", enabled=True, **kwargs)


def test_disabled_and_missing_key_never_send(monkeypatch):
    send = Mock()
    monkeypatch.setattr(wire, "urlopen", send)
    for cfg in (ConversationConfig(llm_provider="openrouter"),
                ConversationConfig(llm_provider="openrouter", openrouter_enabled=True)):
        with pytest.raises(ProviderError):
            create_provider(cfg)
    send.assert_not_called()
    monkeypatch.setenv("OPENROUTER_ENABLED", "true")
    assert ConversationConfig.from_env().llm_provider == "none"


@pytest.mark.parametrize("structured", [False, True])
def test_json_modes_usage_cost_and_backend_routing(monkeypatch, structured):
    send = Mock(return_value=response())
    monkeypatch.setattr(wire, "urlopen", send)
    p = provider(structured_output=structured, model="deepseek/deepseek-v3.2")
    assert call(p).add_semantic_preferences == ["view đẹp"]
    req = send.call_args.args[0]
    payload = json.loads(req.data)
    assert req.full_url == wire.ENDPOINT
    assert payload["model"] == "deepseek/deepseek-v3.2"
    assert payload["response_format"]["type"] == ("json_schema" if structured else "json_object")
    assert payload["provider"] == {"require_parameters": True}
    assert 0 < send.call_args.kwargs["timeout"] <= 30
    assert p.last_usage == {"input_tokens": 12, "output_tokens": 7, "total_tokens": 19}
    assert p.last_cost_usd == .0004
    assert p.last_attempts == 1


@pytest.mark.parametrize("status,code", [(401, "authentication_error"), (403, "authentication_error"),
                                          (429, "rate_limit"), (400, "provider_error"), (503, "provider_error")])
def test_safe_http_errors(monkeypatch, status, code):
    monkeypatch.setattr(wire, "urlopen", Mock(side_effect=HTTPError(wire.ENDPOINT, status,
        "mock-only-secret provider body", {}, None)))
    with pytest.raises(ProviderError) as err:
        call(provider())
    assert err.value.code == code
    assert "mock-only-secret" not in str(err.value)


def test_bounded_retry_and_no_timeout_retry(monkeypatch):
    send = Mock(side_effect=[HTTPError(wire.ENDPOINT, 429, "secret", {}, None), response()])
    monkeypatch.setattr(wire, "urlopen", send)
    pause = Mock()
    monkeypatch.setattr(wire.time, "sleep", pause)
    p = provider(max_retries=1)
    call(p)
    assert p.last_attempts == 2
    pause.assert_called_once()
    send.reset_mock(side_effect=True)
    send.side_effect = URLError(TimeoutError("mock-only-secret"))
    with pytest.raises(ProviderError) as err:
        call(p)
    assert err.value.code == "timeout" and send.call_count == 1
    assert p.last_usage == {} and p.last_cost_usd is None


@pytest.mark.parametrize("content,finish", [({"unknown": 3}, "stop"), (output(), "length")])
def test_invalid_or_truncated_outputs_keep_billable_usage(monkeypatch, content, finish):
    monkeypatch.setattr(wire, "urlopen", Mock(return_value=response(content, finish=finish)))
    p = provider()
    with pytest.raises(ProviderError) as err:
        call(p)
    assert err.value.code == "invalid_output" and p.last_cost_usd == .0004


@pytest.mark.parametrize("kwargs", [{"timeout": float("nan")}, {"max_retries": 3}, {"max_tokens": 0}])
def test_bad_limits(kwargs):
    with pytest.raises(ValueError):
        provider(**kwargs)


def test_environment_keys_are_server_only(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "mock-only-secret")
    from dataclasses import replace
    cfg = replace(ConversationConfig.from_env(), log_enabled=True, log_path=str(tmp_path / "conversation.jsonl"))
    assert "mock-only-secret" not in repr(cfg)
    assert cfg.openrouter_model == "qwen/qwen3-32b"
    monkeypatch.setattr(wire, "urlopen", Mock(return_value=response()))
    turn = process_user_request(UserRequest(session_id="S", message="view đẹp mock-only-secret"), config=cfg)
    assert turn.metadata.llm_called
    assert turn.metadata.provider == "openrouter"
    assert turn.metadata.cost_usd == .0004 and turn.metadata.provider_attempts == 1
    assert turn.state.semantic_preferences == ["view đẹp"]
    text = (tmp_path / "conversation.jsonl").read_text(encoding="utf-8")
    assert "mock-only-secret" not in text
    assert "[REDACTED]" in text
    assert json.loads(text)["cost_usd"] == .0004


@pytest.mark.parametrize("bad", ['{"x":1,"x":2}', '{"x":NaN}', '```json\n{}\n```'])
def test_strict_json_rejects_duplicate_nonfinite_and_fences(monkeypatch, bad):
    body = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": bad}}]}).encode()
    monkeypatch.setattr(wire, "urlopen", Mock(return_value=nullcontext(SimpleNamespace(read=lambda _: body))))
    with pytest.raises(ProviderError) as err:
        call(provider())
    assert err.value.code == "invalid_output"


def test_rule_slm_openrouter_chain_and_rule_bypass(monkeypatch):
    from common.schemas import PreferenceUpdate
    from conversation.slm.base import SLMParseResult
    send = Mock(return_value=response())
    monkeypatch.setattr(wire, "urlopen", send)
    config = ConversationConfig(llm_provider="openrouter", openrouter_enabled=True,
        openrouter_api_key="mock-only-secret", local_slm_enabled=True)
    local = SimpleNamespace(parse=Mock(return_value=SLMParseResult(
        update=PreferenceUpdate(), confidence=0, should_fallback=True)))
    result = process_user_request(UserRequest(session_id="S", message="dưới 80k, view đẹp"),
                                  config=config, slm_provider=local)
    assert result.metadata.slm_fallback and result.metadata.provider == "openrouter"
    assert result.state.hard_constraints["budget_max"] == 80000
    assert result.state.semantic_preferences == ["view đẹp"]
    send.reset_mock()
    local.parse.reset_mock()
    process_user_request(UserRequest(session_id="S", message="dưới 80k"), config=config, slm_provider=local)
    send.assert_not_called()
    local.parse.assert_not_called()


def test_fallback_error_keeps_rule_constraints(monkeypatch):
    from common.schemas import PreferenceUpdate
    from conversation.slm.base import SLMParseResult
    monkeypatch.setattr(wire, "urlopen", Mock(side_effect=TimeoutError("mock-only-secret")))
    local = SimpleNamespace(parse=lambda _: SLMParseResult(
        update=PreferenceUpdate(), confidence=0, should_fallback=True))
    config = ConversationConfig(llm_provider="openrouter", openrouter_enabled=True,
        openrouter_api_key="mock-only-secret", local_slm_enabled=True)
    result = process_user_request(UserRequest(session_id="S", message="dưới 80k, view đẹp"),
                                  config=config, slm_provider=local)
    assert result.metadata.llm_error == "timeout" and result.metadata.partial_result
    assert result.state.hard_constraints["budget_max"] == 80000
    assert result.metadata.cost_usd is None
