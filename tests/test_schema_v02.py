"""Preference v0.2 semantics and the frozen SLM route, strictly offline."""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from common.schemas import PreferenceUpdate, UserPreferenceState, UserRequest
from conversation.config import ConversationConfig
from conversation.interactive.dataset_logger import DatasetLogger
from conversation.interactive.session import InteractiveSession
from conversation.normalization import normalize_update
from conversation.providers.mock import MockProvider
from conversation.providers.gemini_provider import GeminiProvider
from conversation.providers.openai_provider import OpenAIProvider
from conversation.rule_parser import parse_by_rules_detailed
from conversation.service import process_user_request
from conversation.slm.base import SLMParseResult
from conversation.state_manager import update_state
from test_providers import wire_payload


@pytest.mark.parametrize("message,expected", [
    ("tôi đi xe máy", {"context_updates": {"transport_mode": "motorbike"}}),
    ("tôi đi xe máy, bắt buộc có chỗ gửi xe", {"context_updates": {"transport_mode": "motorbike"}, "add_hard_constraints": {"parking": True}}),
    ("có chỗ gửi xe thì tốt", {"add_soft_preferences": {"parking": True}}),
    ("dưới 40k được không", {"add_hard_constraints": {"budget_max": 40000}}),
    ("dưới 40k nhé", {"add_hard_constraints": {"budget_max": 40000}}),
    ("bạn kiếm quán dưới 3km nhé", {"add_hard_constraints": {"max_distance_km": 3}}),
    ("tôi chuyển qua đi xe máy, kiếm quán dưới 3km nhé", {"context_updates": {"transport_mode": "motorbike"}, "add_hard_constraints": {"max_distance_km": 3}}),
    ("gần hơn một chút", {"relative_updates": {"distance": "decrease"}}),
    ("gần gần thôi", {"add_soft_preferences": {"distance": "near"}}),
    ("quán gần đây", {"add_soft_preferences": {"distance": "near"}}),
    ("có thể đi bộ tới, không quá xa", {"context_updates": {"transport_mode": "walking"}, "add_soft_preferences": {"distance": "near"}}),
    ("đi bộ không quá 10 phút", {"context_updates": {"transport_mode": "walking"}, "add_hard_constraints": {"max_travel_time_min": 10}}),
    ("đi bộ trong 1km", {"context_updates": {"transport_mode": "walking"}, "add_hard_constraints": {"max_distance_km": 1}}),
    ("bỏ giới hạn ngân sách", {"remove_preferences": ["hard_constraints.budget_max"]}),
    ("không đi xe máy nữa", {"remove_preferences": ["context.transport_mode"]}),
    ("không thích cay", {"add_negative_preferences": ["spicy"]}),
    ("dị ứng đậu phộng", {"add_hard_constraints": {"allergens_excluded": ["peanut"]}}),
    ("bắt buộc có parking và có parking thì tốt", {"add_hard_constraints": {"parking": True}}),
    ("gần hơn, dưới 3km", {"add_hard_constraints": {"max_distance_km": 3}}),
    ("rẻ hơn, dưới 40k", {"add_hard_constraints": {"budget_max": 40000}}),
    ("phải dưới 100k", {"add_hard_constraints": {"budget_max": 100000}}),
    ("tối nay đi date", {"context_updates": {"occasion": "date", "meal_time": "dinner"}}),
    ("đi ăn với bạn gái", {"context_updates": {"companions": ["partner"]}}),
    ("đi ô tô", {"context_updates": {"transport_mode": "car"}}),
    ("đi xe đạp", {"context_updates": {"transport_mode": "bicycle"}}),
    ("đi xe buýt", {"context_updates": {"transport_mode": "public_transport"}}),
    ("đặt grab", {"context_updates": {"transport_mode": "ride_hailing"}}),
    ("nhóm 2 người", {"context_updates": {"party_size": 2}}),
    ("muốn ăn ramen Nhật", {"set_values": {"food": ["ramen"], "cuisine": ["japanese"]}}),
])
def test_v02_deterministic_cases(message, expected):
    provider = MockProvider()
    result = process_user_request(UserRequest(session_id="S", message=message), provider)
    assert result.preference_update == PreferenceUpdate.model_validate(expected)
    assert not result.metadata.requires_llm
    assert provider.call_count == 0
    assert "relative_updates" not in result.state.context


def test_hybrid_walking_food_and_budget():
    message = "tôi muốn ăn cơm tấm, dưới 50k, có thể đi bộ tới không quá xa"
    provider = MockProvider(callback=lambda **kw: PreferenceUpdate(set_values={"food": ["cơm tấm"]}))
    result = process_user_request(UserRequest(session_id="S", message=message), provider)
    assert provider.call_count == 1
    assert result.preference_update == PreferenceUpdate(set_values={"food": ["cơm tấm"]},
        add_hard_constraints={"budget_max": 50000}, add_soft_preferences={"distance": "near"},
        context_updates={"transport_mode": "walking"})


@pytest.mark.parametrize("message", ["ramen nhưng phải yên tĩnh", "ramen với view đẹp",
                                       "đi xe máy nếu trời không mưa", "tầm 100k thì đẹp"])
def test_unknown_semantics_remain_unresolved(message):
    assert parse_by_rules_detailed(message).requires_llm


@pytest.mark.parametrize("context", [{"party_size": 0}, {"party_size": True}, {"party_size": 2.5},
    {"location": [10, 106]}, {"relative_updates": []}, {"custom": {"nested": 1}},
    {"transport_mode": "spaceship"}, {"transport_mode": 42}, {"companions": "partner"}, {"custom": float("nan")}])
def test_invalid_context_rejected(context):
    with pytest.raises(ValidationError):
        PreferenceUpdate(context_updates=context)


def test_context_merge_paths_precedence_and_immutability():
    old = UserPreferenceState(session_id="S", food=["ramen"], context={"transport_mode": "walking",
        "occasion": "date", "relative_updates": {"distance": "decrease"}},
        hard_constraints={"budget_max": 50000, "parking": True}, soft_preferences={"wifi": True})
    update = PreferenceUpdate(context_updates={"transport_mode": "xe máy", "companions": ["bạn gái"],
        "custom": [1, True, None]}, add_hard_constraints={"parking": True},
        add_soft_preferences={"parking": False}, remove_preferences=["budget_max", "soft_preferences.wifi"],
        relative_updates={"budget": "increase"})
    before = deepcopy((old.model_dump(), update.model_dump()))
    state = update_state(old, update, "S")
    assert state.context == {"transport_mode": "motorbike", "occasion": "date", "companions": ["partner"], "custom": [1, True, None]}
    assert state.hard_constraints == {"parking": True}
    assert state.soft_preferences == {}
    assert before == (old.model_dump(), update.model_dump())
    state = update_state(state, PreferenceUpdate(context_updates={"transport_mode": "car"},
        remove_preferences=["context.transport_mode", "food"]), "S")
    assert "transport_mode" not in state.context and not state.food
    assert state.context["occasion"] == "date"


def test_absolute_and_hard_precedence_in_replacement_containers():
    update = normalize_update(PreferenceUpdate(set_values={"hard_constraints": {"budget_max": 40000},
        "soft_preferences": {"budget_max": 50000}}, add_soft_preferences={"budget_max": 60000},
        relative_updates={"budget": "decrease"}))
    assert not update.relative_updates and not update.add_soft_preferences
    assert update.set_values["soft_preferences"] == {}


def test_soft_absolute_budget_suppresses_relative():
    update = normalize_update(PreferenceUpdate(add_soft_preferences={"budget_max": 100000},
                                              relative_updates={"budget": "increase"}))
    assert update.relative_updates == {}


def test_model_only_transport_does_not_infer_parking():
    result = process_user_request(UserRequest(session_id="S", message="motorbike, nice view"),
        MockProvider(callback=lambda **kw: PreferenceUpdate(context_updates={"transport_mode": "motorbike"},
                                                            add_soft_preferences={"parking": True})))
    assert result.state.context["transport_mode"] == "motorbike"
    assert "parking" not in result.state.soft_preferences


@pytest.mark.parametrize("nested", [False, True])
def test_transport_model_parking_inference_is_discarded(nested):
    output = PreferenceUpdate(set_values={"hard_constraints": {"parking": True}}) if nested else PreferenceUpdate(add_hard_constraints={"parking": True})
    result = process_user_request(UserRequest(session_id="S", message="tôi đi xe máy, view đẹp"),
                                  MockProvider(callback=lambda **kw: output))
    assert result.state.context["transport_mode"] == "motorbike"
    assert "parking" not in result.state.hard_constraints


def test_explicit_soft_parking_beats_model_hard_inference():
    output = PreferenceUpdate(add_hard_constraints={"parking": True})
    result = process_user_request(UserRequest(session_id="S", message="có parking thì tốt, view đẹp"),
                                  MockProvider(callback=lambda **kw: output))
    assert result.state.soft_preferences["parking"] is True
    assert "parking" not in result.state.hard_constraints


def test_hybrid_allergy_keeps_rule_and_model_exclusions():
    # Explicit shellfish stays residual, preserving this hybrid-union test.
    # Broad Vietnamese seafood is now fully rule-parsed as seafood.
    result = process_user_request(UserRequest(session_id="S", message="dị ứng đậu phộng và shellfish"),
        MockProvider(callback=lambda **kw: PreferenceUpdate(add_hard_constraints={"allergens_excluded": ["shellfish"]})))
    assert result.state.hard_constraints["allergens_excluded"] == ["peanut", "shellfish"]


@pytest.mark.parametrize("provider_type", [GeminiProvider, OpenAIProvider])
def test_shared_provider_context_wire_offline(provider_type):
    payload = wire_payload()
    payload["context_updates"] = [{"key": "transport_mode", "value": "motorbike"}]
    provider = provider_type.__new__(provider_type)
    provider.model = "fake-model"
    endpoint = Mock(return_value=SimpleNamespace(text=json.dumps(payload), output_parsed=payload))
    provider._client = SimpleNamespace(models=SimpleNamespace(generate_content=endpoint),
                                      responses=SimpleNamespace(parse=endpoint))
    result = process_user_request(UserRequest(session_id="S", message="xe máy, view đẹp"), provider)
    endpoint.assert_called_once()
    assert result.preference_update.context_updates == {"transport_mode": "motorbike"}
    assert result.state.context["transport_mode"] == "motorbike"


def test_slm_disabled_never_constructed_or_called(monkeypatch):
    monkeypatch.setattr("conversation.slm.router.create_slm_provider", Mock(side_effect=AssertionError))
    slm = Mock()
    llm = MockProvider(callback=lambda **kw: PreferenceUpdate(add_semantic_preferences=["view đẹp"]))
    result = process_user_request(UserRequest(session_id="S", message="view đẹp"), llm, slm_provider=slm)
    slm.parse.assert_not_called()
    assert llm.call_count == 1
    assert not result.metadata.slm_enabled and not result.metadata.slm_called
    assert result.metadata.slm_ms == 0


def test_slm_sufficient_rules_bypass_all_inference():
    slm, llm = Mock(), MockProvider()
    result = process_user_request(UserRequest(session_id="S", message="ramen"), llm,
        config=ConversationConfig(local_slm_enabled=True), slm_provider=slm)
    slm.parse.assert_not_called()
    assert llm.call_count == 0 and result.metadata.slm_ms == 0


def test_slm_confident_route_and_input_isolation():
    request = UserRequest(session_id="S", message="dưới 50k, view đẹp",
        current_state=UserPreferenceState(session_id="S"), previous_results=[{"rank": 1, "restaurant_id": "R1"}])
    before = request.model_dump()
    def parse(data):
        assert data.message == request.message
        assert data.rule_result.update.add_hard_constraints["budget_max"] == 50000
        assert data.previous_results[0].restaurant_id == "R1"
        data.current_state.food.append("mutation")
        data.rule_result.update.add_hard_constraints.clear()
        return SLMParseResult(update=PreferenceUpdate(add_semantic_preferences=["beautiful view"]), confidence=.8)
    llm = MockProvider()
    result = process_user_request(request, llm, config=ConversationConfig(local_slm_enabled=True),
        slm_provider=SimpleNamespace(parse=parse))
    assert llm.call_count == 0 and result.metadata.parser_used == "hybrid_slm"
    assert result.state.hard_constraints["budget_max"] == 50000
    assert result.state.semantic_preferences == ["beautiful view"]
    assert result.metadata.slm_confidence == .8 and not result.metadata.slm_fallback
    assert request.model_dump() == before


@pytest.mark.parametrize("outcome", ["low", "uncertain", "failure", "invalid", "bad_update", "bad_reference", "nan"])
def test_slm_failures_use_external_once(outcome):
    def parse(data):
        if outcome == "failure":
            raise RuntimeError("secret must not leak")
        if outcome == "invalid":
            return {"garbage": True}
        update = {"set_values": {"food": 123}} if outcome == "bad_update" else {"set_values": {"context": {"restaurant_id": "BAD"}}} if outcome == "bad_reference" else {}
        return {"update": update, "confidence": float("nan") if outcome == "nan" else .79 if outcome == "low" else .95,
                "should_fallback": outcome == "uncertain"}
    llm = MockProvider(callback=lambda **kw: PreferenceUpdate(add_semantic_preferences=["view"]))
    result = process_user_request(UserRequest(session_id="S", message="view đẹp"), llm,
        config=ConversationConfig(local_slm_enabled=True), slm_provider=SimpleNamespace(parse=parse))
    assert llm.call_count == 1 and result.metadata.slm_fallback
    assert result.metadata.slm_called and result.metadata.slm_ms >= 0
    assert result.state.semantic_preferences == ["view"]
    assert "secret" not in result.metadata.model_dump_json()


@pytest.mark.parametrize("backend,error", [("disabled", "disabled_backend"), ("future", "slm_unavailable")])
def test_frozen_backend_safe_fallback(backend, error):
    llm = MockProvider(callback=lambda **kw: PreferenceUpdate())
    result = process_user_request(UserRequest(session_id="S", message="view đẹp"), llm,
        config=ConversationConfig(local_slm_enabled=True, local_slm_backend=backend))
    assert result.metadata.slm_error == error and result.metadata.slm_fallback
    assert llm.call_count == 1


def test_slm_config_default_and_environment(monkeypatch):
    config = ConversationConfig.from_env()
    assert (config.local_slm_enabled, config.local_slm_backend, config.local_slm_model, config.local_slm_min_confidence) == (False, "qwen_lora", "", .8)
    monkeypatch.setenv("LOCAL_SLM_ENABLED", "true")
    monkeypatch.setenv("LOCAL_SLM_MIN_CONFIDENCE", "0.9")
    assert ConversationConfig.from_env().local_slm_enabled
    assert ConversationConfig.from_env().local_slm_min_confidence == .9
    monkeypatch.setenv("LOCAL_SLM_MIN_CONFIDENCE", "nan")
    with pytest.raises(ValueError):
        ConversationConfig.from_env()


def test_legacy_reviewed_export_and_context_correction(tmp_path):
    assert PreferenceUpdate.model_validate({}).context_updates == {}
    logger = DatasetLogger(tmp_path, enabled=True)
    record = {"message": "old", "old_state": None, "previous_results": [], "label_status": "accepted",
              "preference_update": {"add_semantic_preferences": ["suitable for a date"]}}
    before = deepcopy(record)
    rows = [json.loads(line) for line in logger.export([record]).read_text(encoding="utf-8").splitlines()]
    assert rows[0]["schema_version"] == "0.2"
    assert rows[0]["target"]["context_updates"] == {}
    assert rows[0]["target"]["add_semantic_preferences"] == ["suitable for a date"]
    assert record == before  # Never relabel historic decisions.
    session = InteractiveSession(provider="rule", directory=tmp_path)
    session.process("ramen")
    session.correct('{"context_updates": {"transport_mode": "motorbike"}}')
    assert session.current_state.context["transport_mode"] == "motorbike"
    assert session.records[0]["schema_version"] == "0.2"
    assert json.loads(session.export().read_text(encoding="utf-8"))["target"]["context_updates"] == {"transport_mode": "motorbike"}


def test_dataset_readiness_is_validation_only(tmp_path):
    import sys
    from pathlib import Path
    monkey_path = str(Path(__file__).resolve().parents[1] / "scripts")
    if monkey_path not in sys.path:
        sys.path.insert(0, monkey_path)
    from check_ai2_slm_dataset import check_data
    row = {"schema_version": "0.2", "input": {"message": "ramen", "old_state": None, "previous_results": []},
           "target": {}, "label_status": "accepted"}
    path = tmp_path / "dataset.jsonl"
    path.write_text("\n".join(json.dumps(value) for value in [row, row, {**row, "schema_version": "0.1"},
        {**row, "label_status": "unreviewed"}]), encoding="utf-8")
    result = check_data(path)
    assert result["valid"] == 2 and result["duplicate_count"] == 1
    assert len(result["errors"]) == 2 and result["training_enabled"] is False
