"""Authored runtime safety checks, never training/benchmark gold."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from common.schemas import PreferenceUpdate, PreviousResult, UserPreferenceState, UserRequest
from conversation.config import ConversationConfig
from conversation.environment import load_env
from conversation.evidence import validate_explicit_evidence
from conversation.providers.mock import MockProvider
from conversation.rule_parser import parse_by_rules_detailed
from conversation.service import process_user_request
from conversation.slm.base import SLMParseResult
from scripts.regress_ai2_adapters import run_case, overlap_audit


def turn(message, payload, state=None, previous=None):
    slm = SimpleNamespace(parse=lambda _: SLMParseResult(update=payload, confidence=.8))
    return process_user_request(UserRequest(session_id="S", message=message, current_state=state,
        previous_results=previous or []), config=ConversationConfig(local_slm_enabled=True), slm_provider=slm)


@pytest.mark.parametrize("message,expected", [
    ("Mình dị ứng hạt mè", ["sesame"]), ("Tôi dị ứng vừng", ["sesame"]),
    ("Mình bị dị ứng sữa và đậu phộng", ["milk", "peanut"]),
    ("I am allergic to sesame and milk", ["sesame", "milk"]),
])
def test_explicit_allergens(message, expected):
    assert parse_by_rules_detailed(message).update.add_hard_constraints["allergens_excluded"] == expected


@pytest.mark.parametrize("message", ["không dị ứng mè", "có thể bị dị ứng sữa", "nếu dị ứng mè thì tránh"])
def test_uncertain_negated_allergies_remain_unresolved(message):
    assert "allergens_excluded" not in parse_by_rules_detailed(message).update.add_hard_constraints


def test_wrong_sesame_target_rejected_and_complete_rules_retained():
    result = turn("Mình dị ứng hạt mè, chọn nơi ánh sáng dịu.",
                  PreferenceUpdate(add_hard_constraints={"allergens_excluded": ["peanut"]}))
    assert result.state.hard_constraints["allergens_excluded"] == ["sesame"]
    assert result.metadata.slm_fallback


def test_omitted_second_allergen_is_restored_by_rule_merge():
    result = turn("Mình dị ứng sữa và đậu phộng, chọn nơi ánh sáng dịu.",
                  PreferenceUpdate(add_hard_constraints={"allergens_excluded": ["peanut"]}))
    assert result.state.hard_constraints["allergens_excluded"] == ["milk", "peanut"]


@pytest.mark.parametrize("removals", [["allergens_excluded"], ["hard_constraints.allergens_excluded"], ["hard_constraints"]])
def test_wifi_turn_cannot_clear_confirmed_allergy(removals):
    state = UserPreferenceState(session_id="S", hard_constraints={"allergens_excluded": ["milk", "peanut"]},
                                soft_preferences={"wifi": True})
    result = turn("Chỉ bỏ wifi, dị ứng đã xác nhận giữ nguyên.", PreferenceUpdate(remove_preferences=removals), state)
    assert result.state.hard_constraints == state.hard_constraints
    assert result.metadata.slm_fallback
    assert state.soft_preferences["wifi"] is True


def test_wifi_delta_is_accepted_without_repeating_confirmed_allergy():
    state = UserPreferenceState(session_id="S", hard_constraints={"allergens_excluded": ["milk"]}, soft_preferences={"wifi": True})
    result = turn("Chỉ bỏ wifi, dị ứng đã xác nhận giữ nguyên.", PreferenceUpdate(remove_preferences=["soft_preferences.wifi"]), state)
    assert not result.metadata.slm_fallback
    assert result.state.hard_constraints == state.hard_constraints and result.state.soft_preferences == {}


def test_reference_missing_mention_uses_actual_selector_and_drops_invented_attributes():
    result = turn("Quán số 2 rẻ hơn nhé.", PreferenceUpdate(references=[{
        "rank": 2, "sentiment": "positive", "wifi": True}], relative_updates={"budget": "decrease"}),
        previous=[PreviousResult(rank=2, restaurant_id="real-id")])
    assert result.preference_update.references == [{"status": "resolved", "rank": 2,
        "restaurant_id": "real-id", "mention": "quán số 2"}]
    assert "relative_updates" not in result.state.context


def test_deictic_reference_rejects_fabricated_facility():
    result = turn("Quán đó nhé.", PreferenceUpdate(add_hard_constraints={"wifi": True}))
    assert result.state.hard_constraints == {}
    assert result.metadata.clarification_required


def test_time_numeric_mismatch_and_service_acceptance():
    with pytest.raises(ValueError):
        validate_explicit_evidence(PreferenceUpdate(add_hard_constraints={"max_travel_time_min": 5}),
                                  "Không quá 15 phút")
    result = turn("Thời gian di chuyển không quá 15 phút, ánh sáng dịu.",
                  PreferenceUpdate(add_hard_constraints={"max_travel_time_min": 15}))
    assert not result.metadata.slm_fallback
    assert not result.metadata.partial_result
    assert result.state.hard_constraints["max_travel_time_min"] == 15


def test_adapter_selection_and_env_loader(monkeypatch, tmp_path):
    assert ConversationConfig.from_env().local_slm_adapter_path.endswith("targeted-v3")
    path = tmp_path / ".env"
    path.write_text("LOCAL_SLM_ADAPTER_VERSION=v4\nLOCAL_SLM_ENABLED=false\nOPENROUTER_ENABLED=false\n", encoding="utf-8")
    load_env(path)
    cfg = ConversationConfig.from_env()
    assert cfg.local_slm_adapter_path == "models/ai2/best_adapter_v4_experimental"
    assert not cfg.local_slm_enabled and not cfg.openrouter_enabled
    monkeypatch.setenv("LOCAL_SLM_ADAPTER_PATH", "custom-adapter")
    assert ConversationConfig.from_env().local_slm_adapter_path == "custom-adapter"
    monkeypatch.setenv("LOCAL_SLM_ADAPTER_VERSION", "v5")
    with pytest.raises(ValueError):
        ConversationConfig.from_env()


def test_harness_exact_scoring_and_no_inference_in_rule_mode():
    case = json.loads((Path(__file__).parent / "data/ai2_adapter_regressions.json").read_text(encoding="utf-8"))[3]
    record = run_case(case)
    assert record["checks"]["state_exact"] and record["checks"]["effective_delta_exact"]
    assert record["checks"]["json_schema_valid"] is None


def test_overlap_audit_flags_near_and_exact_without_altering_corpus(tmp_path):
    path = tmp_path / "train.jsonl"
    path.write_text(json.dumps({"message": "same authored message"}) + "\n", encoding="utf-8")
    before = path.read_bytes()
    audit = overlap_audit([{"id": "a", "message": "same authored message"}], [path])
    assert audit["cases"][0]["exact_overlap"]
    assert not audit["independent_benchmark"] and path.read_bytes() == before
