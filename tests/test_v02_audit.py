"""Audit regressions use synthetic fixtures only; no real labels or inference."""
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from common.schemas import PreferenceUpdate, UserPreferenceState, UserRequest
from conversation.config import ConversationConfig
from conversation.conversation_logger import _redact
from conversation.normalization import normalize_update
from conversation.providers.mock import MockProvider
from conversation.providers.structured import StructuredPreferenceUpdate
from conversation.rule_parser import parse_by_rules_detailed
from conversation.service import process_user_request
from conversation.state_manager import update_state
from test_providers import wire_payload


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("message,key,correct,wrong", [
    ("dưới 50k, view sông", "budget_max", 50000, 60000),
    ("trước 5km, giờ chỉ lấy trong 3km", "max_distance_km", 3, 5),
    ("đi bộ không quá 10 phút, view đẹp", "max_travel_time_min", 10, 20),
])
def test_explicit_numeric_rule_beats_model(message, key, correct, wrong, nested):
    output = PreferenceUpdate(set_values={"hard_constraints": {key: wrong}}) if nested else PreferenceUpdate(add_hard_constraints={key: wrong})
    output.relative_updates = {"budget" if key == "budget_max" else "distance": "decrease"}
    result = process_user_request(UserRequest(session_id="S", message=message), MockProvider(callback=lambda **kw: output))
    assert result.preference_update.add_hard_constraints[key] == correct
    assert result.state.hard_constraints[key] == correct
    assert result.preference_update.relative_updates == {}


@pytest.mark.parametrize("message,output,field,expected", [
    ("có parking thì tốt nhưng thật ra bắt buộc phải có", {"add_hard_constraints": {"parking": True}}, "hard_constraints", {"parking": True}),
    ("tối nay, à thực ra trưa mai", {"context_updates": {"meal_time": "lunch"}}, "context", {"meal_time": "lunch"}),
    ("đi xe máy nhưng đổi sang taxi", {"context_updates": {"transport_mode": "ride_hailing"}}, "context", {"transport_mode": "ride_hailing"}),
])
def test_explicit_later_correction_can_override_partial_rule(message, output, field, expected):
    result = process_user_request(UserRequest(session_id="S", message=message), MockProvider(callback=lambda **kw: PreferenceUpdate(**output)))
    assert getattr(result.state, field) == expected
    if field == "hard_constraints":
        assert result.preference_update.add_soft_preferences == {}


def test_scoped_removal_precedes_conflict_cleanup():
    update = PreferenceUpdate(add_hard_constraints={"wifi": True}, add_soft_preferences={"wifi": True},
        remove_preferences=["hard_constraints.wifi"])
    normalized = normalize_update(update)
    assert normalized.add_hard_constraints == {}
    assert normalized.add_soft_preferences == {"wifi": True}
    assert update_state(None, update, "S").soft_preferences == {"wifi": True}


@pytest.mark.parametrize("hard,soft,expected_paths", [
    ({}, {"budget_max": 50000}, ["soft_preferences.budget_max"]),
    ({"budget_max": 60000}, {"budget_max": 50000}, ["hard_constraints.budget_max", "soft_preferences.budget_max"]),
])
def test_legacy_numeric_removal_uses_existing_scope(hard, soft, expected_paths):
    state = UserPreferenceState(session_id="S", hard_constraints=hard, soft_preferences=soft)
    provider = MockProvider(callback=lambda **kw: PreferenceUpdate(remove_preferences=["budget_max"]))
    result = process_user_request(UserRequest(session_id="S", message="đổi yêu cầu cũ", current_state=state), provider)
    assert result.preference_update.remove_preferences == expected_paths
    assert "budget_max" not in result.state.hard_constraints
    assert "budget_max" not in result.state.soft_preferences


@pytest.mark.parametrize("field", ["food", "cuisine"])
def test_removed_intent_absent_from_effective_update_and_form_still_wins(field):
    output = PreferenceUpdate(set_values={field: ["japanese"]}, remove_preferences=[field])
    request = UserRequest(session_id="S", message="đổi ý nhé")
    result = process_user_request(request, MockProvider(callback=lambda **kw: output))
    assert field not in result.preference_update.set_values
    assert getattr(result.state, field) == []
    request.form = request.form.model_copy(update={field: ["explicit"]})
    result = process_user_request(request, MockProvider(callback=lambda **kw: output))
    assert getattr(result.state, field) == ["explicit"]


@pytest.mark.parametrize("payload", [{"confidence": .99}, {"update": {}, "confidence": True},
                                     {"update": {}, "confidence": "0.99"}])
def test_malformed_slm_result_falls_back(payload):
    llm = MockProvider(callback=lambda **kw: PreferenceUpdate())
    result = process_user_request(UserRequest(session_id="S", message="view đẹp"), llm,
        config=ConversationConfig(local_slm_enabled=True), slm_provider=SimpleNamespace(parse=lambda request: payload))
    assert llm.call_count == 1 and result.metadata.slm_fallback


def test_unavailable_slm_factory_does_not_report_provider_called():
    llm = MockProvider(callback=lambda **kw: PreferenceUpdate())
    result = process_user_request(UserRequest(session_id="S", message="view đẹp"), llm,
        config=ConversationConfig(local_slm_enabled=True, local_slm_backend="unknown"))
    assert not result.metadata.slm_called
    assert result.metadata.slm_confidence is None and result.metadata.slm_fallback
    assert llm.call_count == 1


@pytest.mark.parametrize("key,value", [("location", [10, 106]), ("party_size", 0)])
def test_mutated_context_cannot_bypass_state_validation(key, value):
    update = PreferenceUpdate()
    update.context_updates[key] = value
    with pytest.raises(ValueError):
        update_state(None, update, "S")


@pytest.mark.parametrize("key", ["food", "cuisine", "context", "location"])
def test_soft_wire_constraints_reject_state_fields(key):
    payload = wire_payload()
    payload["add_soft_preferences"] = [{"key": key, "value": "invented"}]
    with pytest.raises(ValidationError):
        StructuredPreferenceUpdate.model_validate(payload).to_update()


def test_redaction_covers_dictionary_keys_in_shared_logger():
    secret = "audit-test-private-credential"
    value = {"context": {secret: "value"}, "usage": {"input_tokens": 4}}
    result = _redact(value, (secret,))
    assert secret not in json.dumps(result)
    assert result["usage"]["input_tokens"] == 4


def test_negated_near_phrase_not_reintroduced_as_preference():
    result = parse_by_rules_detailed("không cần không quá xa")
    assert "distance" not in result.update.add_soft_preferences


def test_allergens_union_across_additions_and_hybrid_replacement():
    old = UserPreferenceState(session_id="S", hard_constraints={"allergens_excluded": ["milk"]})
    output = PreferenceUpdate(set_values={"hard_constraints": {"allergens_excluded": ["shellfish"]}})
    result = process_user_request(UserRequest(session_id="S", message="dị ứng đậu phộng và shellfish", current_state=old),
                                  MockProvider(callback=lambda **kw: output))
    assert set(result.state.hard_constraints["allergens_excluded"]) == {"peanut", "shellfish", "milk"}
    assert old.hard_constraints == {"allergens_excluded": ["milk"]}
    # Explicit direct set/replacement is still possible; additions are additive.
    replaced = update_state(old, PreferenceUpdate(set_values={"hard_constraints": {"allergens_excluded": ["peanut"]}}), "S")
    assert replaced.hard_constraints == {"allergens_excluded": ["peanut"]}


@pytest.mark.parametrize("key,value", [("max_travel_time_min", -1), ("budget_min", -1),
    ("min_rating", 8), ("allergens_excluded", "peanut"), ("parking", "yes")])
def test_known_constraint_validation_matches_public_and_wire(key, value):
    with pytest.raises(ValidationError):
        PreferenceUpdate(add_hard_constraints={key: value})
    payload = wire_payload()
    payload["add_hard_constraints"] = [{"key": key, "value": value}]
    with pytest.raises(ValidationError):
        StructuredPreferenceUpdate.model_validate(payload).to_update()


def test_benchmark_empty_dict_is_an_assertion():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from ai2_tools import subset_checks
    assert subset_checks({}, {"distance": "decrease"}, "relative_updates") == [
        {"field": "relative_updates", "correct": False}]


def test_interactive_latency_includes_slm(tmp_path):
    from conversation.interactive.session import InteractiveSession
    session = InteractiveSession(provider="mock", directory=tmp_path, no_save=True)
    record = session.process("view đẹp")
    assert record["metadata"]["latency"]["slm_ms"] == 0


@pytest.mark.parametrize("message", ["ramen chuyển qua sushi", "ramen, thôi chuyển qua sushi"])
def test_food_replacement_operator_is_not_filler(message):
    assert parse_by_rules_detailed(message).requires_llm


@pytest.mark.parametrize("payload", [{"context_updates": {"food": ["ramen"]}},
    {"set_values": {"context": {"location": {"lat": 10, "lon": 106}}}},
    {"set_values": {"context": {"party_size": 0}}},
    {"add_soft_preferences": {"food": ["ramen"]}}])
def test_alternate_input_paths_cannot_misplace_query_intent(payload):
    with pytest.raises(ValueError):
        update_state(None, PreferenceUpdate(**payload), "S")


def test_multiturn_correction_relative_lifetime_and_food_replacement(tmp_path):
    from conversation.interactive.session import InteractiveSession
    session = InteractiveSession(provider="mock", directory=tmp_path, no_save=True)
    session.process("ramen, tôi đi xe máy")
    first = session.process("tìm gần hơn")
    assert first["preference_update"]["relative_updates"] == {"distance": "decrease"}
    session.process("sushi")
    session.correct(json.dumps({"set_values": {"food": ["cơm tấm"]},
                                "context_updates": {"transport_mode": "walking"}}, ensure_ascii=False))
    corrected = deepcopy(session.current_state.model_dump())
    seen = []
    def parse(**kwargs):
        seen.append(kwargs["current_state"].model_dump())
        return PreferenceUpdate(context_updates={"meal_time": "lunch"})
    session.mock = MockProvider(callback=parse)
    next_turn = session.process("thôi để trưa mai")
    assert seen == [corrected]
    assert next_turn["old_state"] == corrected
    assert next_turn["new_state"]["food"] == ["cơm tấm"]
    assert next_turn["new_state"]["context"] == {"transport_mode": "walking", "meal_time": "lunch"}
    assert next_turn["preference_update"]["relative_updates"] == {}
    assert all("relative_updates" not in row["new_state"]["context"] for row in session.records)


def test_utf8_export_filters_labels_without_relabeling(tmp_path):
    from conversation.interactive.dataset_logger import DatasetLogger
    phrases = ["cơm tấm", "cái thứ hai", "đi xe máy", "đừng quá ồn", "dị ứng đậu phộng"]
    records = [{"message": phrase, "old_state": None, "previous_results": [],
        "label_status": status, "preference_update": {"add_semantic_preferences": [phrase]},
        "correction": {"context_updates": {"transport_mode": "motorbike"}}}
        for phrase in phrases for status in ("accepted", "corrected", "unreviewed", "rejected")]
    before = deepcopy(records)
    logger = DatasetLogger(tmp_path, enabled=True)
    path = logger.export(records)
    payload = path.read_bytes()
    for phrase in phrases:
        assert phrase.encode("utf-8") in payload
    rows = [json.loads(line) for line in payload.decode("utf-8").splitlines()]
    assert len(rows) == 10
    assert {row["label_status"] for row in rows} == {"accepted", "corrected"}
    assert all(row["schema_version"] == "0.2" for row in rows)
    assert all(row["target"]["context_updates"] == {"transport_mode": "motorbike"}
               for row in rows if row["label_status"] == "corrected")
    assert records == before


def test_disabled_path_has_no_slm_or_heavy_imports(monkeypatch):
    import builtins
    real_import = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.startswith(("conversation.slm", "torch", "transformers", "onnxruntime", "google.genai")) or name == "openai":
            raise AssertionError("Disabled route attempted an inference import")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    provider = MockProvider(callback=lambda **kw: PreferenceUpdate())
    result = process_user_request(UserRequest(session_id="S", message="view sông"), provider,
                                  config=ConversationConfig())
    assert provider.call_count == 1
    assert not result.metadata.slm_called and result.metadata.slm_confidence is None
    assert result.metadata.slm_ms == 0 and result.metadata.llm_called


@pytest.mark.parametrize("message", ["quán phù hợp nói chuyện công việc", "quán không quá ồn"])
def test_meaningful_residue_still_unresolved(message):
    assert parse_by_rules_detailed(message).requires_llm


def test_reference_feedback_preserves_turn_event_only():
    results = [{"rank": 1, "restaurant_id": "R001"}, {"rank": 2, "restaurant_id": "R002"}]
    provider = MockProvider(callback=lambda **kw: PreferenceUpdate(references=[
        {"rank": 2, "mention": "cái thứ hai", "sentiment": "positive", "similar_to": True}]))
    first = process_user_request(UserRequest(session_id="S", message="cái thứ hai", previous_results=results), provider)
    assert provider.call_count == 0
    assert first.preference_update.references[0]["restaurant_id"] == "R002"
    second = process_user_request(UserRequest(session_id="S", current_state=first.state, previous_results=results,
        message="cái thứ hai khá ổn nhưng hơi xa, tìm giống nó mà gần hơn"), provider)
    assert second.preference_update.references[0]["similar_to"] == "R002"
    assert second.preference_update.relative_updates == {"distance": "decrease"}
    assert "relative_updates" not in second.state.context


def test_dataset_checker_does_not_echo_invalid_input_secrets(tmp_path):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from check_ai2_slm_dataset import check_data
    row = {"schema_version": "0.2", "label_status": "accepted", "input": {
        "message": "synthetic", "old_state": None, "previous_results": []},
        "target": {"context_updates": {"party_size": "audit-test-private-credential"}}}
    path = tmp_path / "invalid.jsonl"
    path.write_text(json.dumps(row), encoding="utf-8")
    result = check_data(path)
    assert result["errors"] and result["valid"] == 0
    assert "audit-test-private-credential" not in json.dumps(result)


@pytest.mark.parametrize("use_slm", [False, True])
def test_legacy_relative_context_not_sent_back_to_inference(use_slm):
    old = UserPreferenceState(session_id="S", context={"transport_mode": "walking",
        "relative_updates": {"budget": "decrease"}})
    before = old.model_dump()
    seen = []
    def external(**kwargs):
        seen.append(kwargs["current_state"].context)
        return PreferenceUpdate()
    def local(request):
        seen.append(request.current_state.context)
        return {"update": {}, "confidence": .9}
    result = process_user_request(UserRequest(session_id="S", message="view đẹp", current_state=old),
        MockProvider(callback=external), config=ConversationConfig(local_slm_enabled=use_slm),
        slm_provider=SimpleNamespace(parse=local))
    assert seen == [{"transport_mode": "walking"}]
    assert result.preference_update.relative_updates == {}
    assert old.model_dump() == before


@pytest.mark.parametrize("threshold", ["-0.1", "1.1", "nan", "inf", "invalid"])
def test_invalid_slm_configuration_fails_before_inference(monkeypatch, threshold):
    monkeypatch.setenv("LOCAL_SLM_MIN_CONFIDENCE", threshold)
    with pytest.raises(ValueError):
        ConversationConfig.from_env()


def test_walking_reachable_variant_is_near_not_relative():
    result = parse_by_rules_detailed("đi bộ tới được, không quá xa")
    assert result.update.context_updates == {"transport_mode": "walking"}
    assert result.update.add_soft_preferences == {"distance": "near"}
    assert result.update.relative_updates == {}


def test_ambiguous_legacy_parking_removal_removes_both_scopes():
    old = UserPreferenceState(session_id="S", hard_constraints={"parking": True},
                              soft_preferences={"parking": True, "wifi": True})
    result = update_state(old, PreferenceUpdate(remove_preferences=["parking"]), "S")
    assert result.hard_constraints == {}
    assert result.soft_preferences == {"wifi": True}
    assert old.hard_constraints == {"parking": True} and old.soft_preferences["parking"] is True
