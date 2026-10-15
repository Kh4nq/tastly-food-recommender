"""New safety regressions; expectations are separate from frozen diagnostics."""
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from common.schemas import PreferenceUpdate, PreviousResult, UserPreferenceState, UserRequest
from conversation.config import ConversationConfig
from conversation.evidence import AllergyEvidenceError, validate_explicit_evidence
from conversation.reference_resolver import resolve_selector
from conversation.rule_parser import parse_by_rules_detailed
from conversation.service import process_user_request
from conversation.slm.base import SLMParseResult


def turn(message, delta=None, state=None, results=None, provider=None):
    local = SimpleNamespace(parse=lambda _: SLMParseResult(update=delta or PreferenceUpdate(), confidence=.8))
    return process_user_request(UserRequest(session_id="S", message=message, current_state=state,
        previous_results=results or []), provider,
        config=ConversationConfig(local_slm_enabled=True, llm_provider="none"), slm_provider=local)


@pytest.mark.parametrize("message,allergens", [
    ("Bị dị ứng hạt điều", ["cashew"]),
    ("I'm allergic to cashew nuts and milk", ["cashew", "milk"]),
    ("Dị ứng sữa và hạt điều", ["milk", "cashew"]),
    ("Dị ứng hạt điều và đậu phộng", ["cashew", "peanut"]),
])
def test_cashew_is_extensible_canonical_allergen(message, allergens):
    initial = UserPreferenceState(session_id="S", hard_constraints={"allergens_excluded": ["sesame"]})
    result = turn(message, state=initial)
    assert result.state.hard_constraints["allergens_excluded"] == ["sesame", *allergens]
    assert not result.metadata.clarification_required
    assert initial.hard_constraints == {"allergens_excluded": ["sesame"]}


@pytest.mark.parametrize("route", ["slm", "external"])
def test_cashew_substitution_rejected_preserving_prior_allergies(route):
    from conversation.providers.mock import MockProvider
    wrong = PreferenceUpdate(add_hard_constraints={"allergens_excluded": ["peanut"]})
    initial = UserPreferenceState(session_id="S", hard_constraints={"allergens_excluded": ["milk"]})
    provider = MockProvider(callback=lambda **_: wrong) if route == "external" else None
    result = turn("Mình bị dị ứng hạt điều, muốn view lạ", wrong, initial, provider=provider)
    assert result.state.hard_constraints["allergens_excluded"] == ["milk", "cashew"]
    assert result.metadata.slm_fallback and result.metadata.clarification_required
    if provider:
        assert provider.call_count == 1 and result.metadata.llm_error == "invalid_output"


def test_safe_fallback_can_clear_rejection_without_erasing_prior_allergies():
    from conversation.providers.mock import MockProvider
    provider = MockProvider(callback=lambda **_: PreferenceUpdate(add_hard_constraints={"allergens_excluded": ["cashew"]}))
    result = turn("Mình bị dị ứng hạt điều, muốn view lạ",
        PreferenceUpdate(add_hard_constraints={"allergens_excluded": ["peanut"]}),
        UserPreferenceState(session_id="S", hard_constraints={"allergens_excluded": ["milk"]}), provider=provider)
    assert result.metadata.slm_fallback and provider.call_count == 1
    assert not result.metadata.clarification_required
    assert result.state.hard_constraints["allergens_excluded"] == ["milk", "cashew"]


def test_unknown_allergen_cannot_be_substituted_or_remove_known_allergies():
    initial = UserPreferenceState(session_id="S", hard_constraints={"allergens_excluded": ["milk", "sesame"]})
    result = turn("Mình bị dị ứng một loại hạt chưa rõ", PreferenceUpdate(
        add_hard_constraints={"allergens_excluded": ["peanut"]}, remove_preferences=["allergens_excluded"]), initial)
    assert result.metadata.clarification_required
    assert result.state.hard_constraints == initial.hard_constraints


@pytest.mark.parametrize("message", ["Không bị dị ứng hạt điều.", "Nếu bị dị ứng hạt điều thì sao?", "Có thể bị dị ứng hạt điều."])
def test_negated_or_uncertain_cashew_is_not_positive_exclusion(message):
    result = turn(message, PreferenceUpdate(add_hard_constraints={"allergens_excluded": ["cashew"]}))
    assert not result.state.hard_constraints
    assert result.metadata.slm_fallback


def test_wifi_correction_does_not_erase_cashew_or_other_known_allergies():
    initial = UserPreferenceState(session_id="S", hard_constraints={"allergens_excluded": ["milk", "cashew"], "wifi": True})
    result = turn("Chỉ bỏ yêu cầu Wi-Fi, giữ nguyên dị ứng đã xác nhận", PreferenceUpdate(
        remove_preferences=["hard_constraints.wifi", "hard_constraints.allergens_excluded"]), initial)
    assert result.state.hard_constraints["allergens_excluded"] == ["milk", "cashew"]
    assert initial.hard_constraints["wifi"] is True


@pytest.mark.parametrize("message,food", [
    ("Tôi muốn tìm lẩu chay.", "lẩu chay"), ("Phở chay nhé", "phở chay"),
    ("Tìm một món lẩu nấm chay.", "lẩu nấm chay"), ("Tôi muốn phở thuần chay", "phở thuần chay"),
    ("Không muốn thịt; tìm lẩu chay", "lẩu chay"),
])
def test_explicit_vegetarian_dish_preserves_food_and_mandatory_constraint(message, food):
    result = turn(message)
    assert result.state.hard_constraints["vegetarian"] is True
    assert result.state.food == [food]


@pytest.mark.parametrize("message", [
    "Không muốn lẩu chay.", "Không phải phở chay.", "Đừng tìm một món lẩu chay.",
    "Nếu có lẩu chay thì tôi sẽ cân nhắc.", "Tìm phở chay nếu giá rẻ.",
    "Có thể ăn chay.", "Tìm lẩu chay hoặc lẩu bò.",
    'Tìm quán Lẩu Chay ở quận 1.', 'Quán tên Phở Chay có wifi không?',
    'Tìm quán "Lẩu Chay" có chỗ gửi xe.', 'Tên món là "phở chay".',
])
def test_noncommitment_or_name_does_not_create_vegetarian_constraint(message):
    assert "vegetarian" not in parse_by_rules_detailed(message).update.add_hard_constraints
    result = turn(message, PreferenceUpdate(add_hard_constraints={"vegetarian": True}))
    assert "vegetarian" not in result.state.hard_constraints


def test_negated_dietary_phrase_does_not_implicitly_remove_prior_constraint():
    initial = UserPreferenceState(session_id="S", hard_constraints={"vegetarian": True})
    result = turn("Không muốn phở chay", PreferenceUpdate(), initial)
    assert result.state.hard_constraints["vegetarian"] is True


def test_explicit_vegetarian_removal_keeps_state_manager_removal_semantics():
    result = turn("Không cần ăn chay nữa", state=UserPreferenceState(session_id="S", hard_constraints={"vegetarian": True}))
    assert "vegetarian" not in result.state.hard_constraints


def test_conflicting_ordinal_and_id_cannot_resolve_to_wrong_result():
    results = [PreviousResult(rank=2, restaurant_id="real-2"), PreviousResult(rank=3, restaurant_id="real-3")]
    assert resolve_selector({"rank": 3, "mention": "quán số 2", "restaurant_id": "real-3"}, results) == {
        "status": "unresolved", "mention": "quán số 2"}
    result = turn("Chọn quán số 2", PreferenceUpdate(references=[{"rank": 3, "mention": "quán số 2"}]), results=results)
    assert result.state.reference_restaurants == [{"status": "resolved", "rank": 2, "restaurant_id": "real-2", "mention": "quán số 2"}]


def test_missing_rank_preserves_mention_without_untrusted_properties():
    result = turn("Quán số 3 nhé", PreferenceUpdate(references=[{"rank": 3, "restaurant_id": "fabricated", "wifi": True}]),
        results=[PreviousResult(rank=2, restaurant_id="real-2")])
    assert result.preference_update.references == [{"status": "unresolved", "mention": "quán số 3"}]


def test_grounding_does_not_delete_explicit_food_beside_negated_allergy():
    result = turn("Không bị dị ứng mè; tôi muốn ăn phở", PreferenceUpdate(set_values={"food": ["phở"]}))
    assert result.state.food == ["phở"]


def test_allergy_guard_does_not_consume_an_unknown_dish_request_after_comma():
    result = turn("Không bị dị ứng mè, mình muốn bánh cuốn", PreferenceUpdate(set_values={"food": ["bánh cuốn"]}))
    assert result.state.food == ["bánh cuốn"] and not result.metadata.slm_fallback


def test_reference_only_cannot_remove_constraints_or_invent_relative_events():
    initial = UserPreferenceState(session_id="S", food=["sushi"], hard_constraints={"vegetarian": True, "wifi": True})
    result = turn("Chọn quán số 2", PreferenceUpdate(remove_preferences=["food", "hard_constraints.wifi"],
        relative_updates={"budget": "decrease"}, references=[{"rank": 2}]), initial,
        results=[PreviousResult(rank=2, restaurant_id="real-2")])
    assert result.state.food == ["sushi"] and result.state.hard_constraints == initial.hard_constraints
    assert not result.preference_update.relative_updates


def test_reference_with_explicit_wifi_still_accepts_grounded_constraint():
    result = turn("Chọn quán số 2, bắt buộc có Wi-Fi", PreferenceUpdate(add_hard_constraints={"wifi": True},
        references=[{"rank": 2}]), results=[PreviousResult(rank=2, restaurant_id="real-2")])
    assert result.state.hard_constraints == {"wifi": True}
    assert result.state.reference_restaurants[0]["mention"] == "quán số 2"


def test_reference_grounding_keeps_explicit_form_priority_without_fallback():
    local = SimpleNamespace(parse=lambda _: SLMParseResult(update=PreferenceUpdate(references=[{"rank": 2}]), confidence=.8))
    result = process_user_request(UserRequest(session_id="S", message="Chọn quán số 2",
        form={"food": "ramen", "budget_max": 120000}, previous_results=[PreviousResult(rank=2, restaurant_id="real-2")]),
        config=ConversationConfig(local_slm_enabled=True, llm_provider="none"), slm_provider=local)
    assert result.state.food == ["ramen"] and result.state.hard_constraints["budget_max"] == 120000
    assert not result.metadata.slm_fallback and not result.metadata.llm_called


def test_explicit_open_context_outside_bounded_correction_is_preserved():
    delta = PreferenceUpdate(context_updates={"weather": "rainy", "sentiment": "happy"})
    result = turn("Mình vui và hôm nay trời mưa", delta)
    assert result.state.context == delta.context_updates


def test_evidence_validator_rejects_substitution_even_without_parser():
    with pytest.raises(AllergyEvidenceError):
        validate_explicit_evidence(PreferenceUpdate(add_hard_constraints={"allergens_excluded": ["peanut"]}), "Dị ứng hạt điều")


@pytest.mark.parametrize("outer", [False, True])
def test_nested_json_is_controlled_and_keeps_known_usage(monkeypatch, outer):
    from contextlib import nullcontext
    from conversation.providers.base import ProviderError
    from conversation.providers.openrouter_provider import OpenRouterProvider
    nested = "[" * 2000 + "0" + "]" * 2000
    body = nested.encode() if outer else json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": nested}}],
        "usage": {"cost": .001, "prompt_tokens": 15}}).encode()
    monkeypatch.setattr("conversation.providers.openrouter_provider.urlopen", lambda *a, **k:
        nullcontext(SimpleNamespace(read=lambda _: body)))
    provider = OpenRouterProvider(api_key="offline-test", enabled=True)
    with pytest.raises(ProviderError) as caught:
        provider.parse_preference(message="test", current_state=None, previous_results=[])
    assert caught.value.code == "invalid_output" and provider.last_attempts == 1
    if not outer:
        assert provider.last_cost_usd == .001 and provider.last_usage["input_tokens"] == 15


def test_gemini_nested_validation_error_is_controlled(monkeypatch):
    from conversation.providers.base import ProviderError
    from scripts.benchmark_ai2_providers import mock_provider
    from conversation.providers.structured import StructuredPreferenceUpdate
    provider, _ = mock_provider("gemini", "offline-model")
    def nested(*args, **kwargs):
        raise RecursionError("untrusted response")
    monkeypatch.setattr(StructuredPreferenceUpdate, "model_validate_json", nested)
    with pytest.raises(ProviderError) as caught:
        provider.parse_preference(message="test", current_state=None, previous_results=[])
    assert caught.value.code == "invalid_output"
    assert provider.last_usage["input_tokens"] == 12


def test_benchmark_subprocess_inherits_key_only_from_environment_without_logging(tmp_path, monkeypatch):
    # This child exercises the real benchmark/config/provider boundary with a
    # fake transport. No --live flag, no real credential, and offline sockets.
    import uuid
    sentinel = "offline-sentinel-" + uuid.uuid4().hex
    monkeypatch.setenv("OPENROUTER_API_KEY", sentinel)
    child = tmp_path / "mock_child.py"
    child.write_text('''
import json, os, sys
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch
from scripts import benchmark_ai2_providers as bench
from conversation.config import ConversationConfig
from conversation.providers.openrouter_provider import OpenRouterProvider
def inherited_provider(name, model):
    cfg = ConversationConfig.from_env()
    if cfg.openrouter_api_key != os.environ["OPENROUTER_API_KEY"]:
        raise RuntimeError("Environment inheritance failed")
    provider = OpenRouterProvider(api_key=cfg.openrouter_api_key, enabled=True, model=model)
    def fake_send(request, **kwargs):
        if request.get_header("Authorization") != "Bearer " + os.environ["OPENROUTER_API_KEY"]:
            raise RuntimeError("Credential forwarding failed")
        wire = bench.empty_wire()
        # Deliberately echo the fake credential to verify report redaction too.
        provider.benchmark_wire = {"mock_echo": os.environ["OPENROUTER_API_KEY"]}
        body = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(wire)}}]}).encode()
        return nullcontext(SimpleNamespace(read=lambda _: body))
    return provider, patch("conversation.providers.openrouter_provider.urlopen", side_effect=fake_send)
bench.mock_provider = inherited_provider
raise SystemExit(bench.main(["--provider", "qwen32", "--mock", "--max-calls", "1", "--output", sys.argv[1]]))
''', encoding="utf-8")
    report = tmp_path / "child-report.json"
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[1]))
    run = subprocess.run([sys.executable, str(child), str(report)], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, "Mock child failed"
    output = report.read_text(encoding="utf-8")
    assert sentinel not in output + run.stdout + run.stderr
    data = json.loads(output)
    assert data["external_api_calls"] == 0
    assert data["run_summary"]["schema_valid_responses"] == 1
    assert data["cases"][0]["wire_response"]["mock_echo"] != sentinel


def test_guard_comparison_cannot_rewrite_frozen_model_outputs_or_shared_source():
    from copy import deepcopy
    from scripts.benchmark_ai2_freeze import evaluate_case
    from scripts.build_ai2_freeze_suite import build_suite
    from scripts.report_ai2_safety_patch import compare_guard_replay
    delta = PreferenceUpdate(add_hard_constraints={"allergens_excluded": ["sesame"]})
    local = SimpleNamespace(last_response=delta.model_dump_json(),
                            parse=lambda _: SLMParseResult(update=delta, confidence=.8))
    record = evaluate_case(build_suite()["cases"][0], local)
    before = {"suite_sha256": "frozen", "source_checksums": {"src/common/schemas.py": "unchanged"},
              "cases": [record], "summary": {}}
    after = {**deepcopy(before), "mode": "replay"}
    assert compare_guard_replay(before, after)["cases"][0]["raw_response_identical"]
    after["cases"][0]["raw_response"] = "altered"
    with pytest.raises(ValueError, match="frozen model output"):
        compare_guard_replay(before, after)
    after = {**deepcopy(before), "mode": "replay"}
    after["source_checksums"]["src/common/schemas.py"] = "changed"
    with pytest.raises(ValueError, match="outside AI2"):
        compare_guard_replay(before, after)


def test_explicit_local_subset_is_unscored_and_does_not_load_model(tmp_path):
    from scripts.benchmark_ai2_freeze import main
    output = tmp_path / "subset.json"
    assert main(["--case-id", "unknown-allergen-cashew", "--output", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["selected_case_ids"] == ["unknown-allergen-cashew"]
    assert report["complete_suite"] is False and report["independent_gold_count"] == 0
    assert report["external_api_calls"] == 0
