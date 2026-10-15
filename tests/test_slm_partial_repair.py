"""Offline, field-level SLM repair through the real parser/state boundary."""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from common.schemas import PreferenceUpdate, UserRequest
from conversation.config import ConversationConfig
from conversation.models import RuleParseResult
from conversation.providers.base import ProviderError
from conversation.providers.mock import MockProvider
from conversation.service import process_user_request
from conversation.slm.qwen_lora import QwenLoRAProvider


def run(slm_update, repair=None, *, form=None, confidence=.8):
    local = SimpleNamespace(parse=Mock(return_value={"update": slm_update, "confidence": confidence}))
    callback = Mock(return_value=repair)
    if isinstance(repair, Exception):
        callback.side_effect = repair
    external = MockProvider(callback=callback)
    request = UserRequest(session_id="S", message="unparsed ambience", form=form or {})
    result = process_user_request(request, external, config=ConversationConfig(local_slm_enabled=True),
                                  slm_provider=local)
    return result, external, callback


def partial(**extra):
    return {"add_semantic_preferences": ["quiet"], "context_updates": {"occasion": "chat"}, **extra}


def test_valid_slm_never_calls_gemini():
    result, external, _ = run({"add_semantic_preferences": ["quiet"]})
    assert result.state.semantic_preferences == ["quiet"]
    assert external.call_count == 0
    assert result.metadata.slm_called and not result.metadata.slm_fallback
    assert result.metadata.parser_used == "hybrid_slm"


def test_partial_context_repair_preserves_semantics_and_limits_prompt():
    result, external, callback = run(partial(), {
        "context_updates": {"occasion": "casual", "meal_time": "dinner"},
        "add_semantic_preferences": ["yên tĩnh", "suitable for conversation"],
    })
    assert result.state.semantic_preferences == ["quiet", "suitable for conversation"]
    assert result.state.context == {"occasion": "casual"}
    assert external.call_count == 1
    kwargs = callback.call_args.kwargs
    assert "unparsed ambience" not in kwargs["message"]
    assert '"occasion"' in kwargs["message"] and '"chat"' in kwargs["message"]
    assert kwargs["rule_update"].add_semantic_preferences == ["quiet"]
    assert result.metadata.slm_error == "partial_repair"
    assert result.metadata.slm_fallback and result.metadata.llm_called
    assert result.metadata.parser_used == "hybrid_llm"


@pytest.mark.parametrize("use_form", [False, True])
def test_rule_form_and_slm_fields_cannot_be_overwritten(monkeypatch, use_form):
    rule = PreferenceUpdate(add_hard_constraints={"budget_max": 100000}, set_values={"cuisine": ["vietnamese"]})
    monkeypatch.setattr("conversation.parser.parse_by_rules_detailed", lambda _: RuleParseResult(
        update=rule, requires_llm=True))
    result, _, _ = run(partial(set_values={"food": ["phở"], "cuisine": ["thai"]},
                              add_hard_constraints={"budget_max": 200000}), {
        "set_values": {"food": ["pizza"], "hard_constraints": {"budget_max": 150000}},
        "add_hard_constraints": {"budget_max": 150000},
        "context_updates": {"occasion": "casual"},
        "remove_preferences": ["food", "budget_max", "quiet"],
    }, form={"budget_max": 90000} if use_form else None)
    assert result.state.food == ["phở"]
    assert result.state.cuisine == ["vietnamese"]
    assert result.state.hard_constraints["budget_max"] == (90000 if use_form else 100000)
    assert result.state.context == {"occasion": "casual"}
    assert result.state.semantic_preferences == ["quiet"]
    assert result.preference_update.remove_preferences == []


def test_valid_slm_context_is_locked_during_repair():
    result, _, _ = run(partial(context_updates={"occasion": "chat", "meal_time": "lunch"}), {
        "context_updates": {"occasion": "casual", "meal_time": "dinner"},
        "add_negative_preferences": ["quiet"],
    })
    assert result.state.context == {"occasion": "casual", "meal_time": "lunch"}
    assert result.state.negative_preferences == []


def test_rule_already_resolves_rejected_field_without_gemini(monkeypatch):
    monkeypatch.setattr("conversation.parser.parse_by_rules_detailed", lambda _: RuleParseResult(
        update=PreferenceUpdate(context_updates={"occasion": "casual"}), requires_llm=True))
    result, external, _ = run(partial())
    assert result.state.context == {"occasion": "casual"}
    assert result.state.semantic_preferences == ["quiet"]
    assert external.call_count == 0 and not result.metadata.slm_fallback
    assert result.metadata.slm_error == "partial_validation"


@pytest.mark.parametrize("field,opposite", [
    ("semantic_preferences", "negative_preferences"),
    ("negative_preferences", "semantic_preferences"),
])
def test_repair_cannot_negate_accepted_replacement_list(field, opposite):
    result, _, _ = run(partial(set_values={field: ["smoke"]}), {
        "add_" + opposite: ["smoke"], "context_updates": {"occasion": "casual"},
    })
    assert "smoke" in getattr(result.state, field)
    assert "smoke" not in getattr(result.state, opposite)


def test_repair_appends_only_missing_valid_array_items():
    result, _, _ = run(partial(set_values={"food": ["phở", 123]}), {
        "set_values": {"food": ["phở", "ramen"]}, "context_updates": {"occasion": "casual"},
    })
    assert result.state.food == ["phở", "ramen"]
    assert result.state.semantic_preferences == ["quiet"]


def test_relative_events_and_removals_survive_conflicting_repair():
    result, _, _ = run(partial(relative_updates={"budget": "decrease"}, remove_preferences=["spicy"]), {
        "relative_updates": {"budget": "increase"}, "add_negative_preferences": ["cay"],
        "context_updates": {"occasion": "casual"},
    })
    assert result.preference_update.relative_updates == {"budget": "decrease"}
    assert "relative_updates" not in result.state.context
    assert result.preference_update.remove_preferences == ["spicy"]
    assert not result.state.negative_preferences


@pytest.mark.parametrize("failure", [ProviderError("private"), TimeoutError("private"), None, {}, []])
def test_failed_or_unusable_repair_keeps_slm_subset(failure):
    result, external, _ = run(partial(), failure)
    assert result.state.semantic_preferences == ["quiet"]
    assert result.state.context == {}
    assert external.call_count == 1
    assert result.metadata.partial_result and result.metadata.llm_error
    assert result.metadata.slm_error == "partial_repair"
    assert result.metadata.parser_used == "hybrid_slm"
    assert "private" not in result.metadata.model_dump_json()


def test_invalid_repair_never_reaches_state_application(monkeypatch):
    from conversation.state_manager import update_state
    checked = []

    def guarded(current, update, *args):
        assert PreferenceUpdate.model_validate(update.model_dump()) == update
        assert "chat" not in update.context_updates.values()
        assert update.set_values.get("food") != 123
        checked.append(update)
        return update_state(current, update, *args)

    monkeypatch.setattr("conversation.parser.update_state", guarded)
    monkeypatch.setattr("conversation.service.update_state", guarded)
    result, _, _ = run(partial(), {
        "context_updates": {"occasion": "chat"}, "set_values": {"food": 123},
        "add_semantic_preferences": ["suitable for conversation", 123],
    })
    assert checked
    assert result.state.semantic_preferences == ["quiet", "suitable for conversation"]
    assert not result.state.context and not result.state.food
    assert result.metadata.partial_result


def test_nested_constraints_and_array_items_are_independent():
    payload = partial(
        set_values={"hard_constraints": {"budget_max": 100000, "parking": "maybe"}},
        add_negative_preferences=["spicy", 123], remove_preferences=["wifi", 123],
        add_semantic_preferences=["quiet", 123],
    )
    original = deepcopy(payload)
    result, _, _ = run(payload, {
        "add_hard_constraints": {"budget_max": 150000},
        "add_negative_preferences": ["cay", "smoke"],
        "add_semantic_preferences": ["yên tĩnh", "beautiful ambience"],
        "remove_preferences": ["wifi", "outdoor_seating"],
        "context_updates": {"occasion": "casual"},
    })
    assert payload == original
    assert result.state.hard_constraints == {"budget_max": 100000}
    assert result.state.negative_preferences == ["spicy", "smoke"]
    assert result.state.semantic_preferences == ["quiet", "beautiful ambience"]
    assert result.preference_update.remove_preferences == ["wifi", "outdoor_seating"]


@pytest.mark.parametrize("raw", ["not JSON", "{}", "[]"])
def test_malformed_qwen_still_uses_full_fallback(monkeypatch, raw):
    local = QwenLoRAProvider("unused", "unused")
    monkeypatch.setattr(local, "_load", lambda: None)
    monkeypatch.setattr(local, "_generate", lambda _: raw)
    external = MockProvider(callback=lambda **kw: PreferenceUpdate(set_values={"food": ["phở"]}))
    result = process_user_request(UserRequest(session_id="S", message="unparsed ambience"), external,
        config=ConversationConfig(local_slm_enabled=True), slm_provider=local)
    assert external.call_count == 1 and result.state.food == ["phở"]
    assert result.metadata.slm_fallback and result.metadata.slm_error != "partial_repair"


def test_qwen_partial_schema_result_reaches_repair(monkeypatch):
    local = QwenLoRAProvider("unused", "unused")
    payload = {**PreferenceUpdate().model_dump(), **partial()}
    monkeypatch.setattr(local, "_load", lambda: None)
    monkeypatch.setattr(local, "_generate", lambda _: json.dumps(payload))
    external = MockProvider(callback=lambda **_: PreferenceUpdate(context_updates={"occasion": "casual"}))
    result = process_user_request(UserRequest(session_id="S", message="unparsed ambience"), external,
        config=ConversationConfig(local_slm_enabled=True), slm_provider=local)
    assert result.state.semantic_preferences == ["quiet"]
    assert result.state.context == {"occasion": "casual"}
    assert result.metadata.slm_confidence == .8 and result.metadata.slm_error == "partial_repair"


@pytest.mark.parametrize("payload,confidence", [
    ({"context_updates": {"occasion": "chat"}}, .8), (partial(), .79),
    ({"set_values": {"food": 123}}, .8),
    ({"add_hard_constraints": {"parking": True}, "context_updates": {"occasion": "chat"}}, .8),
])
def test_no_valid_subset_or_low_confidence_uses_full_fallback(payload, confidence):
    result, external, callback = run(payload, {"set_values": {"food": ["phở"]}}, confidence=confidence)
    assert external.call_count == 1 and result.state.food == ["phở"]
    assert result.state.semantic_preferences == []
    assert callback.call_args.kwargs["message"] == "unparsed ambience"
    assert result.metadata.slm_error != "partial_repair"
