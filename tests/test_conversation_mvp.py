"""Routing, reference safety, fallback, immutable state and JSONL regression."""

from copy import deepcopy
import json

import pytest

from common.schemas import PreferenceUpdate, PreviousResult, UserPreferenceState, UserRequest
from conversation import parse_by_rules_detailed, process_user_request
from conversation.config import ConversationConfig
from conversation.models import ConversationResult
from conversation.providers import MockProvider
from conversation.reference_resolver import resolve_message_references

RESULTS = [PreviousResult(rank=1, restaurant_id="R001", restaurant_name="A"),
           PreviousResult(rank=2, restaurant_id="R002", restaurant_name="B", menu_item_id="M2",
                          dish_name="Ramen đặc biệt")]


@pytest.mark.parametrize("message,requires", [
    ("Tìm ramen dưới 150k trong vòng 2km", False),
    ("Tìm ramen dưới 150k trong vòng 3km, không ăn cay", False),
    ("Tìm ramen dưới 150k, quán đẹp nhưng đừng quá ồn", True),
    ("Quán thứ hai khá ổn nhưng hơi xa, tìm cái tương tự mà gần hơn", True),
    ("ramen nếu trời mưa còn không thì sushi", True),
    ("không muốn gần hơn", True), ("", False), ("  \n", False),
    ("không ăn chay", True), ("xin chào", True), ("muốn", True),
])
def test_rule_coverage(message, requires):
    result = parse_by_rules_detailed(message)
    assert result.requires_llm is requires
    assert bool(result.unresolved_text) is requires


@pytest.mark.parametrize("message,key", [
    ("không cần quán đẹp nữa", "beautiful ambience"),
    ("bỏ yêu cầu quán đẹp đi", "beautiful ambience"),
    ("không cần yên tĩnh nữa", "quiet"),
    ("bỏ giới hạn 2km", "max_distance_km"),
    ("không cần ăn chay nữa", "vegetarian"),
    ("không quan trọng rating cao nữa", "rating"),
    ("quán đẹp, không cần quán đẹp nữa", "beautiful ambience"),
])
def test_removal(message, key):
    result = process_user_request(UserRequest(session_id="S", message=message,
        current_state=UserPreferenceState(session_id="S", semantic_preferences=["beautiful ambience", "quiet"],
            hard_constraints={"vegetarian": True, "max_distance_km": 2}, soft_preferences={"rating": 4})))
    assert ("hard_constraints." + key if key == "max_distance_km" else key) in result.preference_update.remove_preferences
    assert key not in result.preference_update.add_semantic_preferences
    assert key not in result.state.semantic_preferences
    assert key not in result.state.hard_constraints
    assert key not in result.state.soft_preferences
    assert not result.metadata.llm_called


def test_partial_rule_preserves_known_fields():
    result = parse_by_rules_detailed("Tìm ramen dưới 150k, quán đẹp nhưng đừng quá ồn")
    assert result.update.set_values["food"] == ["ramen"]
    assert result.update.add_hard_constraints["budget_max"] == 150000
    assert "đừng quá ồn" in result.unresolved_text
    assert "ramen" in result.matched_spans


@pytest.mark.parametrize("message,calls", [
    ("Tìm ramen dưới 150k trong 2km", 0),
    ("Muốn chỗ vừa lịch sự để đi với bạn nhưng không quá sang.", 1),
    ("unknown", 1), ("", 0), (None, 0),
])
def test_routing_one_call(message, calls):
    provider = MockProvider({message: PreferenceUpdate()})
    result = process_user_request(UserRequest(session_id="S", message=message), provider)
    assert provider.call_count == calls
    assert result.metadata.llm_called is bool(calls)
    assert result.metadata.parser_used == ("hybrid_llm" if calls else "rule")


def test_form_priority_rule_retention_and_removal_wins():
    message = "ramen budget 200k, quán đẹp nhưng bỏ giới hạn khoảng cách"
    provider = MockProvider({message: PreferenceUpdate(
        add_semantic_preferences=["beautiful ambience", "quiet", "quiet"],
        remove_preferences=["beautiful ambience", "budget_max", "max_distance_km"],
        relative_updates={"budget": "increase", "distance": "decrease"},
        set_values={"food": ["pizza"]},
    )})
    result = process_user_request(UserRequest(session_id="S", message=message,
        form={"budget_max": 150000, "max_distance_km": 3, "food": []}), provider)
    assert result.state.food == []
    assert result.state.hard_constraints == {"budget_max": 150000, "max_distance_km": 3}
    assert result.state.semantic_preferences == ["quiet"]
    assert result.preference_update.relative_updates == {}
    assert result.preference_update.remove_preferences == ["beautiful ambience"]


def test_llm_omission_does_not_drop_rule_data():
    message = "ramen dưới 150k, quán hợp nói chuyện lâu"
    result = process_user_request(UserRequest(session_id="S", message=message),
        MockProvider({message: PreferenceUpdate(add_semantic_preferences=["suitable for conversation"])}))
    assert result.state.food == ["ramen"]
    assert result.state.hard_constraints == {"budget_max": 150000}
    assert result.state.semantic_preferences == ["suitable for conversation"]


@pytest.mark.parametrize("llm_update", [
    PreferenceUpdate(add_hard_constraints={"budget_max": 200000}),
    PreferenceUpdate(set_values={"hard_constraints": {"budget_max": 200000}}),
])
def test_llm_explicit_correction_and_list_deduplication(llm_update):
    message = "dưới 150k, à thực ra ngân sách hai trăm nghìn"
    llm_update = llm_update.model_copy(deep=True)
    llm_update.set_values["food"] = ["ramen", "ramen"]
    result = process_user_request(UserRequest(session_id="S", message=message),
                                 MockProvider({message: llm_update}))
    assert result.state.hard_constraints["budget_max"] == 200000
    assert result.state.food == ["ramen"]


@pytest.mark.parametrize("message,restaurant", [
    ("quán thứ hai", "R002"), ("Cái đầu tiên", "R001"), ("quán B", "R002"),
    ("món thứ 2", "R002"), ("quán A", "R001"), ("món Ramen đặc biệt", "R002"),
])
def test_deterministic_references_without_llm(message, restaurant):
    provider = MockProvider()
    result = process_user_request(UserRequest(session_id="S", message=message, previous_results=RESULTS), provider)
    assert result.preference_update.references[0]["restaurant_id"] == restaurant
    assert provider.call_count == 0
    assert result.state.reference_restaurants == result.preference_update.references


@pytest.mark.parametrize("message", ["quán thứ ba", "quán này", "quán ABC", "cái đầu tiên"])
def test_unresolved_without_context(message):
    result = process_user_request(UserRequest(session_id="S", message=message))
    assert result.metadata.clarification_required
    assert result.preference_update.references[0]["status"] == "unresolved"
    assert "restaurant_id" not in result.preference_update.references[0]


def test_ambiguous_name_and_rank_do_not_pick_arbitrarily():
    duplicate = [*RESULTS, PreviousResult(rank=2, restaurant_id="R003", restaurant_name="B")]
    for message in ("quán B", "quán thứ hai"):
        assert resolve_message_references(message, duplicate)[0]["status"] == "unresolved"


def test_feedback_and_relative_no_arithmetic():
    message = "Cái thứ hai ổn nhưng hơi xa, tìm giống nó mà gần hơn."
    provider = MockProvider({message: PreferenceUpdate(references=[{
        "rank": 2, "mention": "cái thứ hai", "sentiment": "positive", "similar_to": True,
    }], relative_updates={"distance": "decrease"})})
    result = process_user_request(UserRequest(session_id="S", message=message, previous_results=RESULTS,
        current_state=UserPreferenceState(session_id="S", hard_constraints={"max_distance_km": 3})), provider)
    assert provider.call_count == 1
    assert len(result.preference_update.references) == 1
    ref = result.state.reference_restaurants[0]
    assert ref["restaurant_id"] == ref["similar_to"] == "R002"
    assert ref["sentiment"] == "positive"
    assert ref["menu_item_id"] == "M2"
    assert "relative_updates" not in result.state.context
    assert result.state.hard_constraints == {"max_distance_km": 3}


@pytest.mark.parametrize("ref", [
    {"restaurant_id": "HALLUCINATION", "similar_to": True},
    {"rank": 2, "restaurant_id": "HALLUCINATION"},
    "HALLUCINATION", {"mention": "quán này", "similar_to": True},
])
def test_llm_cannot_invent_ids(ref):
    result = process_user_request(UserRequest(session_id="S", message="feedback", previous_results=RESULTS),
        MockProvider({"feedback": PreferenceUpdate(references=[ref])}))
    assert all("restaurant_id" not in item and "similar_to" not in item
               for item in result.state.reference_restaurants)
    assert result.metadata.clarification_required


@pytest.mark.parametrize("payload", [
    {"set_values": {"food": 123}}, {"relative_updates": {"budget": "double"}},
    {"add_hard_constraints": {"max_distance_km": -2}},
    {"set_values": {"context": {"similar_to": "FAKE"}}},
    {"set_values": {"reference_restaurants": ["FAKE"]}}, None,
])
def test_invalid_llm_output_falls_back(payload):
    provider = MockProvider(callback=lambda **kwargs: payload)
    result = process_user_request(UserRequest(session_id="S", message="ramen dưới 150k, bí ẩn"), provider)
    assert result.metadata.partial_result
    assert result.metadata.llm_error
    assert result.state.food == ["ramen"]
    assert result.state.hard_constraints == {"budget_max": 150000}
    assert provider.call_count == 1


@pytest.mark.parametrize("error", [TimeoutError("secret-token"), RuntimeError("secret-token")])
def test_provider_error_preserves_partial_data(error):
    def fail(**kwargs):
        raise error
    provider = MockProvider(callback=fail)
    result = process_user_request(UserRequest(session_id="S", message="ramen dưới 150k, chỗ thú vị"), provider)
    assert result.state.food == ["ramen"]
    assert result.state.hard_constraints == {"budget_max": 150000}
    assert result.metadata.partial_result
    assert result.metadata.parser_used == "rule_fallback"
    assert "secret-token" not in result.model_dump_json()
    assert provider.call_count == 1


def test_missing_provider_and_empty_form_only():
    result = process_user_request(UserRequest(session_id="S", message="unknown"))
    assert not result.metadata.llm_called
    assert result.metadata.llm_error == "provider_unavailable"
    assert result.metadata.partial_result
    result = process_user_request(UserRequest(session_id="S", form={"food": "phở", "budget_max": 0}))
    assert result.state.food == ["phở"]
    assert result.state.hard_constraints == {"budget_max": 0}
    assert not result.metadata.partial_result


def test_immutability_even_when_provider_mutates_its_inputs():
    request = UserRequest(session_id="S", message="ramen dưới 150k, bí ẩn", previous_results=RESULTS,
                          current_state=UserPreferenceState(session_id="S", food=["phở"]))
    before = deepcopy(request.model_dump())
    def mutate(**kwargs):
        kwargs["current_state"].food.append("pizza")
        kwargs["previous_results"][0].restaurant_id = "mutated"
        kwargs["rule_update"].add_hard_constraints.clear()
        return PreferenceUpdate(add_semantic_preferences=["quiet"])
    result = process_user_request(request, MockProvider(callback=mutate))
    result.state.food.append("sushi")
    assert request.model_dump() == before
    assert result.preference_update.set_values["food"] == ["ramen"]
    assert result.rule_result.update.add_hard_constraints == {"budget_max": 150000}


def test_json_roundtrip_and_latency():
    result = process_user_request(UserRequest(session_id="S", message="ramen"))
    assert ConversationResult.model_validate_json(result.model_dump_json()) == result
    assert result.metadata.total_ms >= result.metadata.rule_parse_ms >= 0
    assert result.metadata.llm_ms == 0
    assert result.metadata.latency_ms == result.metadata.total_ms


def test_logging_enabled_disabled_append_and_redaction(tmp_path):
    path = tmp_path / "nested" / "conversation.jsonl"
    request = UserRequest(session_id="S", user_id="U", message="ramen")
    process_user_request(request, config=ConversationConfig(log_path=str(path)))
    assert not path.exists()
    config = ConversationConfig(log_enabled=True, log_path=str(path), openai_api_key="test-secret")
    process_user_request(request, config=config)
    process_user_request(UserRequest(session_id="S", message="test-secret Authorization: Bearer abc"), config=config)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[0]["session_id"] == "S"
    assert rows[0]["timestamp"]
    for key in ("message", "parser_used", "llm_called", "provider", "requires_llm",
                "preference_update", "latency_ms", "rule_parse_ms", "llm_ms", "total_ms", "error"):
        assert key in rows[0]
    assert "test-secret" not in path.read_text(encoding="utf-8")
    assert "Bearer abc" not in path.read_text(encoding="utf-8")


def test_logging_failure_does_not_crash(tmp_path):
    result = process_user_request(UserRequest(session_id="S", message="ramen"),
        config=ConversationConfig(log_enabled=True, log_path=str(tmp_path)))
    assert result.state.food == ["ramen"]
    assert result.metadata.logging_error == "log_write_failed"


def test_identity_mismatch_rejected_before_llm():
    provider = MockProvider()
    with pytest.raises(ValueError, match="different session"):
        process_user_request(UserRequest(session_id="S", message="unknown",
            current_state=UserPreferenceState(session_id="OTHER")), provider)
    assert provider.call_count == 0


def test_offline_demo_traces(monkeypatch):
    from conversation.demo import run_examples
    # Explicit mock/config keeps demo offline even if user's env selects a real API.
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    traces = run_examples()
    assert len(traces) == 6
    assert [trace["mock_call_count"] for trace in traces] == [0, 1, 0, 1, 0, 1]
    assert all(trace["external_llm_calls"] == 0 for trace in traces)
    assert traces[3]["UserPreferenceState"]["semantic_preferences"] == ["beautiful ambience", "quiet"]
    assert traces[4]["UserPreferenceState"]["semantic_preferences"] == []
    assert traces[5]["UserPreferenceState"]["reference_restaurants"][0]["similar_to"] == "R002"
