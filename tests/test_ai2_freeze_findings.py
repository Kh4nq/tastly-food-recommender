"""Approved safety fixes: regressions, no model/data/API access.

These are separate new regressions, not changes to frozen benchmark labels.
The original assertions remain unchanged after the team's patch approval.
"""
from types import SimpleNamespace

import pytest

from common.schemas import PreferenceUpdate, PreviousResult, UserPreferenceState, UserRequest
from conversation.config import ConversationConfig
from conversation.service import process_user_request
from conversation.rule_parser import parse_by_rules_detailed
from conversation.slm.base import SLMParseResult


def replay(message, output, current=None, results=None):
    local = SimpleNamespace(parse=lambda _: SLMParseResult(update=output.model_copy(deep=True), confidence=.8))
    return process_user_request(UserRequest(session_id="S", message=message, current_state=current,
        previous_results=results or []), config=ConversationConfig(local_slm_enabled=True, llm_provider="none"), slm_provider=local)


def test_negated_sesame_does_not_become_food_selection():
    turn = replay("Không bị dị ứng mè.", PreferenceUpdate(set_values={"food": ["mè"]}))
    assert turn.state.food == []


def test_time_correction_does_not_invent_sentiment_context():
    state = UserPreferenceState(session_id="S", context={"meal_time": "dinner", "party_size": 3})
    turn = replay("Tối nay, à thực ra trưa mai.", PreferenceUpdate(context_updates={
        "meal_time": "lunch", "party_size": 3, "sentiment": "negative"}), state)
    assert turn.state.context == {"meal_time": "lunch", "party_size": 3}


@pytest.mark.parametrize("message", ["Tôi muốn tìm lẩu chay.", "Tìm một món lẩu nấm chay."])
def test_positive_vegetarian_hotpot_has_mandatory_constraint(message):
    assert parse_by_rules_detailed(message).update.add_hard_constraints.get("vegetarian") is True


def test_ordinal_selection_does_not_invent_facility():
    turn = replay("Chọn quán số 2.", PreferenceUpdate(add_hard_constraints={"wifi": True},
        references=[{"rank": 2, "mention": "quán số 2"}]),
        results=[PreviousResult(rank=2, restaurant_id="real-r")])
    assert turn.state.hard_constraints == {}


def test_unrecognized_allergen_does_not_silently_become_peanut():
    turn = replay("Mình bị dị ứng hạt điều.", PreferenceUpdate(add_hard_constraints={"allergens_excluded": ["peanut"]}))
    assert turn.metadata.clarification_required
    assert "peanut" not in turn.state.hard_constraints.get("allergens_excluded", [])


def test_missing_rank_does_not_duplicate_unresolved_reference():
    turn = replay("Quán số 3 nhé.", PreferenceUpdate(references=[{"rank": 3, "similar_to": False}]),
                  results=[PreviousResult(rank=2, restaurant_id="real-r")])
    assert turn.preference_update.references == [{"status": "unresolved", "mention": "quán số 3"}]


def test_openrouter_nested_json_error_is_controlled(monkeypatch):
    import json
    from contextlib import nullcontext
    from conversation.providers.openrouter_provider import OpenRouterProvider
    from conversation.providers.base import ProviderError
    content = "[" * 2000 + "0" + "]" * 2000
    body = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": content}}]}).encode()
    monkeypatch.setattr("conversation.providers.openrouter_provider.urlopen",
        lambda *a, **k: nullcontext(SimpleNamespace(read=lambda _: body)))
    provider = OpenRouterProvider(api_key="mock-key", enabled=True)
    with pytest.raises(ProviderError):
        provider.parse_preference(message="view", current_state=None, previous_results=[])


@pytest.mark.parametrize("message,known", [
    ("Tôi không dị ứng mè nhưng bị dị ứng sữa.", ["milk"]),
    ("Tôi không dị ứng sữa nhưng bị dị ứng đậu phộng.", ["peanut"]),
])
def test_positive_rule_evidence_preserves_allergy_despite_global_model_removal(message, known):
    turn = replay(message, PreferenceUpdate(add_hard_constraints={"allergens_excluded": known},
                                           remove_preferences=["allergens_excluded"]))
    assert turn.state.hard_constraints["allergens_excluded"] == known
