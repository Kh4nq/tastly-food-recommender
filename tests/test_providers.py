"""Exercise official-SDK adapter boundaries using local fake SDK objects."""

import builtins
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from common.schemas import PreferenceUpdate, PreviousResult, UserPreferenceState, UserRequest
from conversation import parse_by_rules_detailed, process_user_request
from conversation.config import ConversationConfig, create_provider
from conversation.prompts import SYSTEM_PROMPT, build_context
from conversation.providers import MockProvider, ProviderError
from conversation.providers.gemini_provider import GeminiProvider
from conversation.providers.openai_provider import OpenAIProvider
from conversation.providers.structured import StructuredPreferenceUpdate


def wire_payload():
    return {
        "set_values": {"food": None, "cuisine": None, "location": None},
        "add_hard_constraints": {"budget_max": None, "max_distance_km": None,
                                 "vegetarian": None, "rating": None},
        "add_soft_preferences": [{"key": "occasion", "value": "friends"}],
        "add_semantic_preferences": ["quiet"], "add_negative_preferences": [],
        "remove_preferences": [], "references": [],
        "relative_updates": {"budget": "increase", "distance": "decrease"},
    }


def test_structured_projection_validates_and_converts():
    parsed = StructuredPreferenceUpdate.model_validate(wire_payload()).to_update()
    assert parsed == PreferenceUpdate(add_semantic_preferences=["quiet"],
        add_soft_preferences={"occasion": "friends"},
        relative_updates={"budget": "increase", "distance": "decrease"})
    invalid = wire_payload()
    invalid["explanation"] = "No prose allowed"
    with pytest.raises(ValidationError):
        StructuredPreferenceUpdate.model_validate(invalid)


def test_wire_schema_has_closed_objects_and_required_properties():
    def check(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for item in node.values():
                check(item)
        elif isinstance(node, list):
            for item in node:
                check(item)
    check(StructuredPreferenceUpdate.model_json_schema())


@pytest.mark.parametrize("provider_type", [OpenAIProvider, GeminiProvider])
@pytest.mark.parametrize("outcome", ["success", "invalid", "timeout", "empty"])
def test_real_adapter_one_call_without_network(monkeypatch, provider_type, outcome):
    if provider_type is OpenAIProvider:
        parsed = StructuredPreferenceUpdate.model_validate(wire_payload()) if outcome == "success" else None
        if outcome == "invalid":
            parsed = {"invalid": True}
        endpoint = Mock(return_value=SimpleNamespace(output_parsed=parsed))
        client = SimpleNamespace(responses=SimpleNamespace(parse=endpoint))
        constructor = Mock(return_value=client)
        monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=constructor))
    else:
        payload = json.dumps(wire_payload()) if outcome == "success" else "invalid prose"
        if outcome == "empty":
            payload = None
        endpoint = Mock(return_value=SimpleNamespace(text=payload))
        client = SimpleNamespace(models=SimpleNamespace(generate_content=endpoint))
        constructor = Mock(return_value=client)
        types = SimpleNamespace(HttpOptions=lambda **kwargs: kwargs,
                                HttpRetryOptions=lambda **kwargs: kwargs)
        genai = SimpleNamespace(Client=constructor, types=types)
        monkeypatch.setitem(sys.modules, "google", SimpleNamespace(genai=genai))
        monkeypatch.setitem(sys.modules, "google.genai", genai)
    if outcome == "timeout":
        endpoint.side_effect = TimeoutError("Authorization: secret-key")
    provider = provider_type(api_key="secret-key", model="configured-test-model")
    result = process_user_request(UserRequest(session_id="S", message="ramen dưới 150k, nói chuyện lâu"), provider)
    endpoint.assert_called_once()
    kwargs = endpoint.call_args.kwargs
    assert kwargs["model"] == "configured-test-model"
    assert result.metadata.llm_called
    assert "secret-key" not in result.model_dump_json()
    assert result.state.food == ["ramen"]
    assert result.state.hard_constraints == {"budget_max": 150000}
    if outcome == "success":
        assert result.metadata.parser_used == "hybrid_llm"
        assert result.state.semantic_preferences == ["quiet"]
    else:
        assert result.metadata.partial_result
        expected_error = "timeout" if outcome == "timeout" else "invalid_output"
        assert result.metadata.llm_error == expected_error
    if provider_type is OpenAIProvider:
        assert constructor.call_args.kwargs["max_retries"] == 0
        assert kwargs["text_format"] is StructuredPreferenceUpdate
        assert kwargs["instructions"] == SYSTEM_PROMPT
    else:
        assert constructor.call_args.kwargs["http_options"]["retry_options"]["attempts"] == 1
        assert kwargs["config"]["response_json_schema"] == StructuredPreferenceUpdate.model_json_schema()
        assert kwargs["config"]["automatic_function_calling"]["disable"] is True


@pytest.mark.parametrize("provider_type,sdk", [(OpenAIProvider, "openai"), (GeminiProvider, "google")])
def test_missing_sdk_is_lazy_and_explicit(monkeypatch, provider_type, sdk):
    original = builtins.__import__
    def missing(name, *args, **kwargs):
        if name == sdk or name.startswith(sdk + "."):
            raise ImportError("SDK absent")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", missing)
    with pytest.raises(ProviderError, match="Install"):
        provider_type(api_key="unused", model="unused")
    assert process_user_request(UserRequest(session_id="S", message="ramen")).state.food == ["ramen"]


@pytest.mark.parametrize("provider_type,key", [(OpenAIProvider, "OPENAI"), (GeminiProvider, "GEMINI")])
def test_missing_credentials(provider_type, key):
    with pytest.raises(ProviderError, match=key):
        provider_type(api_key=None, model=None)


def test_env_configuration_and_mock_without_keys(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("CONVERSATION_LOG_ENABLED", "true")
    monkeypatch.setenv("CONVERSATION_LOG_PATH", str(tmp_path / "events.jsonl"))
    config = ConversationConfig.from_env()
    assert config.log_enabled
    assert isinstance(create_provider(config), MockProvider)
    result = process_user_request(UserRequest(session_id="S", message="unknown"))
    assert result.metadata.llm_called
    assert result.metadata.partial_result  # Unconfigured mock never silently claims success.
    assert (tmp_path / "events.jsonl").exists()
    assert "credential" not in repr(ConversationConfig(openai_api_key="credential"))


def test_prompt_context_contains_inputs_and_no_form_override():
    state = UserPreferenceState(session_id="S", hard_constraints={"budget_max": 150000})
    rule = PreferenceUpdate(relative_updates={"distance": "decrease"})
    results = [PreviousResult(rank=2, restaurant_id="R2")]
    context = json.loads(build_context(message="gần hơn", current_state=state,
                                       previous_results=results, rule_update=rule))
    assert context["current_state"] == state.model_dump()
    assert context["rule_update"] == rule.model_dump()
    assert context["previous_results"] == [results[0].model_dump()]
    assert context["message"] == "gần hơn"


CASES = json.loads((Path(__file__).parent / "data/conversation_cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", [case for case in CASES if "requires_llm" in case], ids=lambda case: case["id"])
def test_dataset_routing_coverage(case):
    # Historical permission-as-increase labels remain frozen in the file.
    # Under current policy that clause is unresolved, so inference is required.
    expected = True if case["id"] == "relative-both-permissive" else case["requires_llm"]
    assert parse_by_rules_detailed(case["message"]).requires_llm is expected
