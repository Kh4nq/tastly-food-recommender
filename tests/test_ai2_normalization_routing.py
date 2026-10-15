"""Category-level offline normalization, routing, and labeling regressions."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unicodedata
from unittest.mock import Mock

import pytest

from common.schemas import PreferenceUpdate, PreviousResult, UserPreferenceState, UserRequest
from conversation.config import ConversationConfig
from conversation.labeling.leakage import LeakageIndex
from conversation.labeling.models import PromptSample, ReviewRecord
from conversation.labeling.review import build_queue, export_records, review_item
from conversation.labeling.storage import digest
from conversation.labeling.teacher import label_samples
from conversation.labeling.validation import validate_label
from conversation.normalization import normalize_update
from conversation.parser import parse_user_input_detailed
from conversation.providers.gemini_provider import GeminiProvider
from conversation.providers.mock import MockProvider
from conversation.providers.structured import StructuredPreferenceUpdate
from conversation.rule_parser import parse_by_rules_detailed
from conversation.slm.base import SLMParseResult
from conversation.state_manager import update_state


CUISINES = [
    ("vietnamese", ("Việt", "Việt Nam", "đồ Việt", "Vietnamese")),
    ("korean", ("Hàn", "Hàn Quốc", "đồ Hàn", "Korean")),
    ("japanese", ("Nhật", "Nhật Bản", "món Nhật", "Japanese")),
    ("chinese", ("Hoa", "Trung Quốc", "món Hoa", "Chinese")),
    ("thai", ("Thái", "Thái Lan", "đồ Thái", "Thai")),
    ("italian", ("Ý", "Italia", "món Ý", "Italian")),
    ("western", ("Tây", "phương Tây", "đồ Tây", "Western")),
]


@pytest.mark.parametrize("canonical,aliases", CUISINES)
@pytest.mark.parametrize("source", ["rule", "provider", "form", "state"])
def test_cuisine_aliases_share_one_boundary(canonical, aliases, source):
    for alias in aliases:
        alias = unicodedata.normalize("NFD", "  " + alias.upper() + "  ")
        payload = PreferenceUpdate(set_values={"cuisine": [alias, canonical]})
        before = payload.model_dump()
        provider = MockProvider(callback=lambda **kw: payload)
        if source == "rule":
            update = parse_by_rules_detailed(alias).update
        elif source == "state":
            state = update_state(None, payload, "S")
            assert state.cuisine == [canonical]
            update = normalize_update(payload)
        else:
            request = UserRequest(session_id="S", message="unparsed ambience" if source == "provider" else None)
            if source == "form":
                request.form.cuisine = [alias, canonical]
            update = parse_user_input_detailed(request, provider, config=ConversationConfig()).preference_update
        assert update.set_values["cuisine"] == [canonical]
        assert payload.model_dump() == before
        assert normalize_update(update) == update


@pytest.mark.parametrize("field,alias,canonical", [
    ("transport_mode", "xe máy", "motorbike"), ("transport_mode", "motorbike", "motorbike"),
    ("transport_mode", "đi bộ", "walking"), ("transport_mode", "walking", "walking"),
    ("transport_mode", "đi ô tô", "car"), ("transport_mode", "đi xe đạp", "bicycle"),
    ("transport_mode", "đi metro", "public_transport"), ("transport_mode", "đi taxi", "ride_hailing"),
    ("occasion", "đi date", "date"), ("occasion", "gia đình", "family"),
    ("occasion", "tiếp khách", "business"), ("occasion", "ăn mừng", "celebration"),
    ("meal_time", "sáng nay", "breakfast"), ("meal_time", "trưa nay", "lunch"),
    ("meal_time", "tối nay", "dinner"), ("meal_time", "ăn khuya", "late_night"),
    ("companions", ["gia đình", "family"], ["family"]),
    ("companions", ["bạn gái", "partner"], ["partner"]),
    ("companions", ["đồng nghiệp", "colleagues"], ["colleagues"]),
])
@pytest.mark.parametrize("replacement", [False, True])
def test_context_aliases_in_deltas_and_replacements(field, alias, canonical, replacement):
    data = {field: alias}
    update = PreferenceUpdate(**({"set_values": {"context": data}} if replacement else {"context_updates": data}))
    actual = update.set_values["context"] if replacement else update.context_updates
    assert actual == {field: canonical}
    assert update_state(None, update, "S").context == {field: canonical}


@pytest.mark.parametrize("phrase,meaning", [
    ("yên tĩnh", "quiet"), ("quán đẹp", "beautiful ambience"),
    ("chỗ chill", "relaxed ambience"), ("phù hợp nói chuyện", "suitable for conversation"),
])
def test_known_semantics_canonicalize_add_set_state_and_removal(phrase, meaning):
    rule = parse_by_rules_detailed(phrase).update
    model = normalize_update(PreferenceUpdate(add_semantic_preferences=[phrase, meaning]))
    assert model == rule
    state = UserPreferenceState(session_id="S", semantic_preferences=[phrase, meaning])
    removed = update_state(state, PreferenceUpdate(remove_preferences=[phrase]), "S")
    assert removed.semantic_preferences == []
    replacement = normalize_update(PreferenceUpdate(set_values={"semantic_preferences": [phrase, meaning]}))
    assert replacement.set_values["semantic_preferences"] == [meaning]
    assert state.semantic_preferences == [phrase, meaning]


@pytest.mark.parametrize("food", ["mì quảng", "bánh căn", "bún mắm", "Hủ tiếu Nam Vang"])
def test_unknown_food_and_semantic_text_are_preserved(food):
    payload = PreferenceUpdate(set_values={"food": [food], "cuisine": ["Regional cuisine"]},
        add_semantic_preferences=["ánh sáng dịu để đọc sách"],
        add_negative_preferences=["mùi khói"],
        add_soft_preferences={"service_mode": "tại quán", "dietary": "custom", "spice_level": "ít cay"})
    assert normalize_update(payload) == payload
    assert parse_by_rules_detailed(food).requires_llm


@pytest.mark.parametrize("message,key,value", [
    ("hôm nay ngân sách tối đa 120 nghìn được không", "budget_max", 120000),
    ("giúp mình tìm giá dưới 85k nhé", "budget_max", 85000),
    ("mức giá không quá 175 ngàn", "budget_max", 175000),
    ("budget tối đa 65000 đồng", "budget_max", 65000),
    ("ngân sách thì dưới 40k", "budget_max", 40000),
    ("khoảng cách trong vòng 2km được không", "max_distance_km", 2),
    ("khoảng cách tối đa 3,5km nhé", "max_distance_km", 3.5),
    ("bắt buộc khoảng cách dưới 1km", "max_distance_km", 1),
    ("đi bộ dưới 12 phút thôi", "max_travel_time_min", 12),
])
def test_attached_domain_words_do_not_cause_provider_calls(message, key, value):
    provider = MockProvider(callback=lambda **kw: pytest.fail("Fully parsed input called inference"))
    result = parse_user_input_detailed(UserRequest(session_id="S", message=message), provider, config=ConversationConfig())
    assert result.preference_update.add_hard_constraints[key] == value
    assert not result.metadata.requires_llm and not result.metadata.llm_called
    assert result.rule_result.unresolved_text is None
    assert not result.preference_update.relative_updates


@pytest.mark.parametrize("message", [
    "tối đa 120k nhưng muốn quán thật yên tĩnh", "giá dưới 80k nếu có thể",
    "dưới 90k, khoảng cách", "trong 2km, ngân sách", "món phở, món lạ",
    "món sushi nhưng không ăn sống", "ngân sách dưới 85k mỗi người",
    "không muốn ngân sách dưới 90k", "không thích món Hàn",
    "không thích món phở", "phở nếu hôm nay có thì thôi", "phở rating cao",
    "có parking thì tốt nhưng bắt buộc có mái che", "đi xe máy, cần chỗ an toàn",
    "bữa tối sau 22 giờ", "nhóm 4 người có trẻ nhỏ", "ăn với gia đình đông người",
    "đi date, có phòng riêng", "rẻ hơn nhiều", "ramen chuyển qua sushi",
    "món Nhật hoặc món Hàn", "ngân sách", "khoảng cách", "giá", "món", "nhé",
])
def test_meaningful_residual_still_routes_to_provider(message):
    provider = MockProvider(callback=lambda **kw: PreferenceUpdate())
    result = parse_user_input_detailed(UserRequest(session_id="S", message=message), provider, config=ConversationConfig())
    assert result.metadata.requires_llm and result.rule_result.unresolved_text
    assert provider.call_count == 1


@pytest.mark.parametrize("message", ["phở theo ý mình", "đi với Thái", "phở phía tây", "hoa trên bàn"])
def test_ambiguous_country_words_are_not_cuisine_intent(message):
    result = parse_by_rules_detailed(message)
    assert "cuisine" not in result.update.set_values
    assert result.requires_llm


@pytest.mark.parametrize("message", [
    "Muốn ăn bánh cuốn, không phải chọn ẩm thực Trung Quốc.",
    "không phải ẩm thực Trung Quốc",
    "không phải muốn ăn món Hàn",
    "chẳng phải chọn món Nhật",
    "không thích ẩm thực Trung Quốc",
    "không muốn chọn món Hàn",
    "đừng chọn đồ Thái",
])
def test_negated_cuisine_is_not_a_positive_rule(message):
    result = parse_by_rules_detailed(message)
    assert result.update == PreferenceUpdate()
    assert result.requires_llm and result.unresolved_text
    assert not result.matched_spans


@pytest.mark.parametrize("message,cuisines", [
    ("Muốn ăn bánh cuốn, không phải chọn ẩm thực Trung Quốc.", []),
    ("Muốn ăn bánh cuốn, thích ẩm thực Trung Quốc", ["chinese"]),
    ("Muốn ăn bánh cuốn, không phải chọn món Hàn, thích ẩm thực Trung Quốc", ["chinese"]),
    ("Muốn ăn bánh cuốn, thích ẩm thực Trung Quốc, không phải chọn món Hàn", ["chinese"]),
])
def test_cuisine_rules_merge_with_food_only_slm_update(message, cuisines):
    raw = PreferenceUpdate(set_values={"food": ["bánh cuốn"]})
    slm = SimpleNamespace(parse=Mock(return_value=SLMParseResult(update=raw, confidence=.8)))
    external = MockProvider(callback=lambda **kw: pytest.fail("Accepted SLM must not call external inference"))
    result = parse_user_input_detailed(
        UserRequest(session_id="S", message=message), external,
        config=ConversationConfig(local_slm_enabled=True), slm_provider=slm,
    )
    expected_rule = {"cuisine": cuisines} if cuisines else {}
    assert result.rule_result.update.set_values == expected_rule
    assert result.preference_update == PreferenceUpdate(set_values={"food": ["bánh cuốn"], **expected_rule})
    assert result.metadata.parser_used == "hybrid_slm"
    assert not result.metadata.slm_fallback
    slm.parse.assert_called_once()
    assert external.call_count == 0
    state = update_state(None, result.preference_update, "S")
    assert state.food == ["bánh cuốn"] and state.cuisine == cuisines


@pytest.mark.parametrize("message,expected", [
    ("hôm nay mình muốn món Hàn nhé", {"set_values": {"cuisine": ["korean"]}}),
    ("món ăn phở nhé", {"set_values": {"food": ["phở"]}}),
    ("có parking thì tốt", {"add_soft_preferences": {"parking": True}}),
    ("có chỗ gửi xe thì tốt nhé", {"add_soft_preferences": {"parking": True}}),
    ("bắt buộc có parking", {"add_hard_constraints": {"parking": True}}),
    ("phải có chỗ đậu xe", {"add_hard_constraints": {"parking": True}}),
    ("không thích cay", {"add_negative_preferences": ["spicy"]}),
    ("đừng cay nhé", {"add_negative_preferences": ["spicy"]}),
    ("dị ứng đậu phộng", {"add_hard_constraints": {"allergens_excluded": ["peanut"]}}),
    ("dị ứng lạc", {"add_hard_constraints": {"allergens_excluded": ["peanut"]}}),
    ("rẻ hơn", {"relative_updates": {"budget": "decrease"}}),
    ("rẻ hơn, dưới 40k", {"add_hard_constraints": {"budget_max": 40000}}),
    ("gần hơn, trong 2km", {"add_hard_constraints": {"max_distance_km": 2}}),
    ("bỏ ngân sách", {"remove_preferences": ["hard_constraints.budget_max"]}),
    ("không cần parking nữa", {"remove_preferences": ["hard_constraints.parking", "soft_preferences.parking"]}),
])
def test_precedence_and_category_semantics(message, expected):
    result = parse_by_rules_detailed(message)
    assert result.update == PreferenceUpdate.model_validate(expected)
    assert not result.requires_llm


def wire_payload():
    return {"set_values": {"food": ["mì quảng"], "cuisine": ["Hàn", "Korean"], "location": None},
            "add_hard_constraints": [], "add_soft_preferences": [],
            "add_semantic_preferences": ["yên tĩnh", "quiet"], "add_negative_preferences": ["đồ cay"],
            "context_updates": [{"key": "occasion", "value": "đi date"}],
            "remove_preferences": [], "references": [], "relative_updates": {"budget": None, "distance": None}}


def test_gemini_wire_to_candidate_validation_review_export(monkeypatch, tmp_path):
    endpoint = Mock(return_value=SimpleNamespace(text=json.dumps(wire_payload())))
    client = SimpleNamespace(models=SimpleNamespace(generate_content=endpoint), close=lambda: None)
    genai = SimpleNamespace(Client=lambda **kw: client, types=SimpleNamespace(
        HttpOptions=lambda **kw: kw, HttpRetryOptions=lambda **kw: kw))
    monkeypatch.setitem(sys.modules, "google", SimpleNamespace(genai=genai))
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    sample = PromptSample(sample_id="fake-gemini", category="test", message="mì quảng với không gian như đã mô tả")
    index = LeakageIndex([])
    labels, _ = label_samples([sample], tmp_path / "teacher.jsonl", index, provider="gemini",
        provider_factory=lambda: GeminiProvider(api_key="offline-placeholder", model="fake-model"))
    endpoint.assert_called_once()
    label = labels[0]
    assert label.status == "completed" and not label.error
    assert label.teacher_prediction["set_values"]["cuisine"] == ["Hàn", "Korean"]
    candidate = label.candidate
    assert candidate["set_values"] == {"food": ["mì quảng"], "cuisine": ["korean"]}
    assert candidate["add_semantic_preferences"] == ["quiet"]
    assert candidate["add_negative_preferences"] == ["spicy"]
    assert candidate["context_updates"] == {"occasion": "date"}
    assert validate_label(sample, candidate, index).passed
    item = build_queue([sample], labels, index)[0]
    accepted = review_item(item, "accepted", index)
    training, excluded = export_records([item], [accepted], index)
    assert not excluded and training[0].target.model_dump(mode="json") == candidate
    assert accepted.original_teacher_prediction == label.teacher_prediction


@pytest.mark.parametrize("action", ["accepted", "corrected", "rejected", "skipped", None])
def test_export_review_gate_remains_explicit(action, tmp_path):
    index = LeakageIndex([])
    sample = PromptSample(sample_id="gate", category="cuisine", message="hôm nay món Hàn nhé")
    labels, _ = label_samples([sample], tmp_path / "teacher.jsonl", index)
    item = build_queue([sample], labels, index)[0]
    records = [] if action is None else [review_item(item, action, index, correction=item.teacher.candidate)]
    training, excluded = export_records([item], records, index)
    assert bool(training) is (action in {"accepted", "corrected"})
    assert bool(excluded) is (action not in {"accepted", "corrected"})


def test_noncanonical_historical_labels_block_export_without_rewriting(tmp_path):
    index = LeakageIndex([])
    sample = PromptSample(sample_id="legacy", category="cuisine", message="món Hàn nhé")
    labels, _ = label_samples([sample], tmp_path / "teacher.jsonl", index)
    labels[0].candidate["set_values"]["cuisine"] = ["Hàn"]
    item = build_queue([sample], labels, index)[0]
    before = deepcopy(item.model_dump())
    assert "noncanonical_cuisine" in item.validation.errors
    with pytest.raises(ValueError, match="noncanonical_cuisine"):
        review_item(item, "accepted", index)
    old_review = ReviewRecord(sample_id=sample.sample_id, item_hash=digest(item), action="accepted",
        original_candidate=item.teacher.candidate, original_teacher_prediction=item.teacher.teacher_prediction,
        final_label=item.teacher.candidate)
    training, excluded = export_records([item], [old_review], index)
    assert not training and "noncanonical_cuisine" in excluded[0]["reason"]
    assert item.model_dump() == before


@pytest.mark.parametrize("field,values,valid", [
    ("cuisine", ["Hàn"], False), ("cuisine", ["Regional cuisine"], True),
    ("food", ["mì quảng"], True), ("semantic_preferences", ["yên tĩnh"], False),
    ("semantic_preferences", ["ánh sáng dịu"], True), ("negative_preferences", ["đồ cay"], False),
])
def test_label_validator_only_flags_known_aliases(field, values, valid):
    sample = PromptSample(sample_id="canonical", category="test", message="món ăn tùy chọn")
    result = validate_label(sample, {"set_values": {field: values}}, LeakageIndex([]))
    assert result.passed is valid


def test_constraint_key_validation_and_extensible_values_remain_unchanged():
    payload = wire_payload()
    payload["add_hard_constraints"] = [{"key": " BUDGET_MAX ", "value": 50000}]
    payload["add_soft_preferences"] = [{"key": " SERVICE_MODE ", "value": "tại quán"}]
    update = normalize_update(StructuredPreferenceUpdate.model_validate(payload).to_update())
    assert update.add_hard_constraints == {"budget_max": 50000}
    assert update.add_soft_preferences == {"service_mode": "tại quán"}
    payload["add_hard_constraints"] = [{"key": "parking", "value": "có"}]
    with pytest.raises(ValueError):
        StructuredPreferenceUpdate.model_validate(payload)


@pytest.mark.parametrize("phrase,expected", [
    ("ăn với gia đình và với bạn bè", ["family", "friends"]),
    ("ăn với bạn bè, với bạn gái", ["friends", "partner"]),
    ("với gia đình và với gia đình", ["family"]),
])
def test_companion_lists_preserve_all_conjoined_groups(phrase, expected):
    result = parse_by_rules_detailed(phrase)
    assert not result.requires_llm
    assert result.update.context_updates == {"companions": expected}


@pytest.mark.parametrize("phrase", ["với gia đình hoặc với bạn bè", "với bạn bè nhưng thật ra với gia đình"])
def test_companion_alternatives_and_corrections_stay_unresolved(phrase):
    assert parse_by_rules_detailed(phrase).requires_llm


@pytest.mark.parametrize("alias", ["đậu phộng", "lạc", "PEANUT"])
@pytest.mark.parametrize("replacement", [False, True])
def test_known_allergen_aliases_across_boundaries(alias, replacement):
    constraints = {"allergens_excluded": [alias, "peanut", "unknown allergen"]}
    payload = PreferenceUpdate(**({"set_values": {"hard_constraints": constraints}} if replacement
                                  else {"add_hard_constraints": constraints}))
    before = payload.model_dump()
    normalized = normalize_update(payload)
    actual = normalized.set_values["hard_constraints"] if replacement else normalized.add_hard_constraints
    assert actual["allergens_excluded"] == ["peanut", "unknown allergen"]
    state = UserPreferenceState(session_id="S", hard_constraints={"allergens_excluded": ["lạc"]})
    assert update_state(state, normalized, "S").hard_constraints == actual
    assert payload.model_dump() == before
    sample = PromptSample(sample_id="allergen", category="allergy", message="dị ứng đậu phộng")
    assert "noncanonical_allergens_excluded" in validate_label(sample, payload, LeakageIndex([])).errors
    assert validate_label(sample, normalized, LeakageIndex([])).passed


def test_multiturn_removal_reference_and_relative_lifetime():
    state = update_state(None, parse_by_rules_detailed("món Hàn, ngân sách dưới 85k, đi xe máy").update, "S")
    assert state.cuisine == ["korean"] and state.hard_constraints["budget_max"] == 85000
    relative = parse_by_rules_detailed("rẻ hơn").update
    state = update_state(state, relative, "S")
    assert state.hard_constraints["budget_max"] == 85000
    assert "relative_updates" not in state.context
    provider = MockProvider(callback=lambda **kw: pytest.fail("Resolved reference needs no inference"))
    parsed = parse_user_input_detailed(UserRequest(session_id="S", current_state=state, message="cái thứ hai",
        previous_results=[PreviousResult(rank=2, restaurant_id="UNCHANGED-R2", menu_item_id="UNCHANGED-M2")]),
        provider, config=ConversationConfig())
    assert parsed.preference_update.references[0]["restaurant_id"] == "UNCHANGED-R2"
    assert parsed.preference_update.references[0]["menu_item_id"] == "UNCHANGED-M2"
    state = update_state(state, PreferenceUpdate(remove_preferences=["budget_max", "context.transport_mode"]), "S")
    assert not state.hard_constraints and not state.context and state.cuisine == ["korean"]


def test_deterministic_audit_has_no_false_resolved_controls_or_inconsistencies(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts/audit_ai2_routing.py"
    spec = importlib.util.spec_from_file_location("audit_ai2_routing", path)
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    # No benchmark, datasets, or provider access is needed to generate/run it.
    monkeypatch.setattr(Path, "read_text", lambda *a, **kw: pytest.fail("Audit read a data file"))
    assert audit.audit_pool() == audit.audit_pool()
    assert audit.audit_pool(1) != audit.audit_pool(2)
    report = audit.run_audit()
    assert report["summary"]["total"] == len({r["message"] for r in report["rows"]}) == 240
    for row in report["rows"]:
        assert not row["flags"], row
        assert row["requires_llm"] == row["expected_requires_llm"], row
    assert all(p["consistent"] for p in report["normalization"])
