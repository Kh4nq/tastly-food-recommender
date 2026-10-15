"""Offline regression coverage for residue, canonical values and vague distance."""

import unicodedata

import pytest

from common.schemas import PreferenceUpdate, PreviousResult, UserPreferenceState, UserRequest
from conversation import parse_by_rules_detailed, process_user_request
from conversation.normalization import normalize_update
from conversation.providers import MockProvider
from conversation.state_manager import update_state


@pytest.mark.parametrize("message,field,expected", [
    ("Cho mình ăn ramen", "set_values", {"food": ["ramen"]}),
    ("Hôm nay muốn phở", "set_values", {"food": ["phở"]}),
    ("Mình chọn sushi", "set_values", {"food": ["sushi"]}),
    ("Trong vòng 2km thôi", "add_hard_constraints", {"max_distance_km": 2}),
    ("Dưới 150k thôi", "add_hard_constraints", {"budget_max": 150000}),
    ("Xa quá, tìm gần hơn đi. Đắt thêm một chút cũng được.", "relative_updates",
     {"distance": "decrease", "budget": "increase"}),
    ("đắt quá, rẻ hơn đi", "relative_updates", {"budget": "decrease"}),
    ("xa quá tìm gần hơn đi", "relative_updates", {"distance": "decrease"}),
    ("cho tôi ăn sushi nha!", "set_values", {"food": ["sushi"]}),
])
def test_benign_residue_routes_without_provider(message, field, expected):
    provider = MockProvider()
    result = process_user_request(UserRequest(session_id="S", message=message), provider)
    assert getattr(result.preference_update, field) == expected
    assert not result.rule_result.requires_llm
    assert result.rule_result.unresolved_text is None
    assert not result.metadata.llm_called
    assert provider.call_count == 0


@pytest.mark.parametrize("message", [
    "Tìm ramen nhưng phải yên tĩnh", "Tìm ramen có view sông",
    "Muốn quán đẹp để đi date nhưng đừng quá ồn",
    "Cái thứ hai khá ổn nhưng hơi xa, tìm quán giống nó mà gần hơn",
    "xa quá", "đắt quá", "xa quá, rẻ hơn đi", "đắt quá, gần hơn đi",
    "không xa quá, gần hơn đi", "ramen nếu hôm nay có thì thôi",
    "ramen thôi nhưng phải có view sông", "cho mình", "hôm nay", "nhé",
    "ramen nhãnha", "ramen cho sushi mình", "ramen xa quá, gần hơn nếu có thể",
])
def test_meaningful_residue_still_calls_provider(message):
    provider = MockProvider({message: PreferenceUpdate()})
    result = process_user_request(UserRequest(session_id="S", message=message), provider)
    assert result.rule_result.requires_llm
    assert result.rule_result.unresolved_text
    assert provider.call_count == 1


@pytest.mark.parametrize("message", ["gần", "gần gần", "quán gần đây", "kiếm quán nào gần gần thôi"])
def test_absolute_near_is_soft_without_previous_distance(message):
    result = process_user_request(UserRequest(session_id="S", message=message), MockProvider())
    assert result.preference_update.add_soft_preferences == {"distance": "near"}
    assert result.preference_update.relative_updates == {}
    assert result.state.soft_preferences == {"distance": "near"}
    assert "relative_updates" not in result.state.context
    assert not result.metadata.requires_llm


@pytest.mark.parametrize("message,direction", [
    ("gần hơn", "decrease"), ("gần hơn chút", "decrease"),
    ("kiếm cái gần hơn", "decrease"),
])
def test_comparative_distance_remains_relative(message, direction):
    result = parse_by_rules_detailed(message)
    assert result.update.relative_updates == {"distance": direction}
    assert result.update.add_soft_preferences == {}
    assert not result.requires_llm


@pytest.mark.parametrize("message", ["không gần", "không muốn quán gần đây", "đừng tìm gần hơn"])
def test_negated_distance_is_not_positive(message):
    result = parse_by_rules_detailed(message)
    assert not result.update.add_soft_preferences
    assert not result.update.relative_updates
    assert result.requires_llm


@pytest.mark.parametrize("alias", ["Nhật", "nhật", "Japanese", "đồ Nhật", unicodedata.normalize("NFD", "Nhật")])
@pytest.mark.parametrize("source", ["rule", "llm", "form"])
def test_cuisine_is_provider_independent(alias, source):
    request = UserRequest(session_id="S", message=alias if source == "rule" else "unknown")
    payload = PreferenceUpdate(set_values={"cuisine": [alias]})
    provider = MockProvider({"unknown": payload})
    if source == "form":
        request.message = None
        request.form.cuisine = [alias]
    before = request.model_dump()
    result = process_user_request(request, provider)
    assert result.preference_update.set_values["cuisine"] == ["japanese"]
    assert result.state.cuisine == ["japanese"]
    assert request.model_dump() == before
    assert payload.set_values["cuisine"] == [alias]
    assert provider.call_count == (1 if source == "llm" else 0)


@pytest.mark.parametrize("alias", ["đồ cay", "cay", "spicy", "spicy food"])
@pytest.mark.parametrize("container", ["add", "set"])
def test_negative_aliases_across_llm_and_state(alias, container):
    payload = PreferenceUpdate(**({"add_negative_preferences": [alias, "spicy"]} if container == "add"
                                 else {"set_values": {"negative_preferences": [alias, "spicy"]}}))
    before = payload.model_dump()
    result = process_user_request(UserRequest(session_id="S", message="unknown"),
                                  MockProvider(callback=lambda **kwargs: payload))
    assert result.state.negative_preferences == ["spicy"]
    normalized = result.preference_update
    assert (normalized.add_negative_preferences if container == "add"
            else normalized.set_values["negative_preferences"]) == ["spicy"]
    assert payload.model_dump() == before


def test_benchmark_negative_preserves_unresolved_semantics():
    message = "Không muốn ăn đồ cay, tìm món Nhật nhẹ nhàng một chút."
    provider = MockProvider({message: PreferenceUpdate(set_values={"cuisine": ["Nhật"]},
        add_negative_preferences=["đồ cay"], add_semantic_preferences=["nhẹ nhàng"])})
    result = process_user_request(UserRequest(session_id="S", message=message), provider)
    assert result.rule_result.requires_llm
    assert "nhẹ nhàng" in result.rule_result.unresolved_text
    assert result.state.cuisine == ["japanese"]
    assert result.state.negative_preferences == ["spicy"]
    assert result.state.semantic_preferences == ["nhẹ nhàng"]


def test_normalization_is_pure_idempotent_and_preserves_free_text():
    phrases = ["beautiful ambience", "suitable for a date", "quiet riverside atmosphere", "cay"]
    payload = PreferenceUpdate(set_values={"cuisine": ["Nhật", "Japanese", "Regional cuisine"],
        "soft_preferences": {"custom": ["Nhật"]}}, add_semantic_preferences=phrases,
        add_negative_preferences=["spicy food", "spicy", "too much oil"])
    before = payload.model_dump()
    normalized = normalize_update(payload)
    assert normalize_update(normalized) == normalized
    assert normalized.set_values["cuisine"] == ["japanese", "Regional cuisine"]
    assert normalized.add_negative_preferences == ["spicy", "too much oil"]
    assert normalized.add_semantic_preferences == phrases
    normalized.set_values["soft_preferences"]["custom"].append("changed")
    assert payload.model_dump() == before


def test_state_normalizes_legacy_aliases_and_removal_without_mutation():
    state = UserPreferenceState(session_id="S", cuisine=["Nhật", "japanese"],
                                negative_preferences=["đồ cay", "spicy"])
    update = PreferenceUpdate(add_negative_preferences=["spicy food"], remove_preferences=["cay"])
    before_state, before_update = state.model_dump(), update.model_dump()
    result = update_state(state, update, "S")
    assert result.cuisine == ["japanese"]
    assert result.negative_preferences == []
    assert state.model_dump() == before_state
    assert update.model_dump() == before_update


def test_ordinal_reference_keeps_deterministic_route():
    provider = MockProvider()
    result = process_user_request(UserRequest(session_id="S", message="cái thứ hai",
        previous_results=[PreviousResult(rank=2, restaurant_id="R002")]), provider)
    assert result.preference_update.references[0]["restaurant_id"] == "R002"
    assert provider.call_count == 0
    assert not result.metadata.requires_llm
