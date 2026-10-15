"""Independent counterexamples for the preparation review; all transports mocked."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from common.schemas import PreferenceUpdate, UserPreferenceState, UserRequest
from conversation.config import ConversationConfig
from conversation.preprocessing import prepare_input
from conversation.providers.mock import MockProvider
from conversation.service import process_user_request


ENABLED = ConversationConfig(translation_enabled=True)


def translator(answer):
    return SimpleNamespace(translate=Mock(return_value=answer))


@pytest.mark.parametrize("source,wrong", [
    ("I'm allergic to shellfish", "dị ứng sữa"),
    ("I'm allergic to milk", "dị ứng trứng"),
    ("I want dinner", "Tôi muốn ăn trưa"),
    ("I am not allergic to milk but I'm allergic to eggs", "Tôi dị ứng sữa nhưng không dị ứng trứng"),
    ("I want dinner but not lunch", "Tôi không muốn ăn tối nhưng muốn ăn trưa"),
    ("I must have parking but I'd prefer air conditioning", "Tôi ưu tiên có parking nhưng phải có điều hòa"),
])
def test_review_semantic_counterexamples_reject_and_fall_back(source, wrong):
    callback = Mock(return_value=PreferenceUpdate())
    result = process_user_request(UserRequest(session_id="S", message=source), MockProvider(callback=callback),
                                  config=ENABLED, translator=translator(wrong))
    assert result.metadata.translation_attempted and not result.metadata.translation_succeeded
    assert result.metadata.translation_error == "translation_rejected"
    assert result.metadata.parsed_message == result.metadata.original_message == source
    if source == "I'm allergic to milk":
        # Translation is still rejected. The original English allergy is now
        # fully rule-parsed, so a paid fallback is correctly bypassed.
        callback.assert_not_called()
        assert result.state.hard_constraints["allergens_excluded"] == ["milk"]
    else:
        assert callback.call_args.kwargs["message"] == source


@pytest.mark.parametrize("source,translated", [
    ("I'm allergic to shellfish", "Tôi dị ứng động vật có vỏ"),
    ("I'm allergic to milk", "Tôi dị ứng sữa"),
    ("I'm allergic to eggs", "Tôi dị ứng trứng"),
    ("I'm allergic to peanuts and milk", "Tôi dị ứng đậu phộng và sữa"),
    ("I am not allergic to milk but I'm allergic to eggs", "Tôi không dị ứng sữa nhưng dị ứng trứng"),
    ("I want dinner", "Tôi muốn ăn tối"),
    ("I want lunch", "Tôi muốn ăn trưa"),
    ("I want breakfast", "Tôi muốn ăn sáng"),
])
def test_known_safety_and_meal_translations_can_pass(source, translated):
    prepared = prepare_input(UserRequest(session_id="S", message=source), ENABLED, translator(translated))
    assert prepared.translation_succeeded and prepared.message == translated


@pytest.mark.parametrize("source", [
    "I'm allergic to lupin", "I'm allergic to something in the sauce",
    "I'm allergic to milk unless it is cooked", "I might be allergic to milk",
])
def test_unverifiable_allergy_input_skips_translation(source):
    tr = translator("Tôi dị ứng sữa")
    prepared = prepare_input(UserRequest(session_id="S", message=source), ENABLED, tr)
    assert not prepared.translation_attempted and not prepared.translation_succeeded
    assert prepared.message == source
    tr.translate.assert_not_called()


@pytest.mark.parametrize("source,translated,masked", [
    ("Find a vegan restaurant", "Tìm quán thuần chay", "Find a vegan restaurant"),
    ("Find a cheap restaurant", "Tìm quán rẻ", "Find a cheap restaurant"),
    ("Find bun cha under 100k", "Tìm AI2KEEP0X dưới AI2KEEP1X", "Find AI2KEEP0X under AI2KEEP1X"),
    ("I want halal food", "Tôi muốn món halal", "I want halal food"),
    ("Find a pescatarian restaurant", "Tìm quán phục vụ chế độ pescatarian", "Find a pescatarian restaurant"),
    ("Find an Italian restaurant", "Tìm quán Ý", "Find an Italian restaurant"),
])
def test_english_frames_accept_open_content(source, translated, masked):
    tr = translator(translated)
    prepared = prepare_input(UserRequest(session_id="S", message=source), ENABLED, tr)
    assert prepared.translation_attempted and prepared.translation_succeeded
    assert tr.translate.call_args.args == (masked,)
    if "bun cha" in source:
        assert prepared.message == "Tìm bun cha dưới 100k"


@pytest.mark.parametrize("source", [
    "bun cha", "vegan", "halal", "Cho tôi quán rẻ", "Find a vegan quán",
    "I want ăn chay", "Find bun cha với bạn", "Find a restaurant cho minh",
    "tôi muốn halal food", "minh muon cheap restaurant",
    "Find quán yên tĩnh under 100k", "Find quan yen tinh under 100k",
    "I want quán yên tĩnh under 100k", "Find a restaurant near cho minh under 100k",
    "I want an chay",
])
def test_vietnamese_and_uncertain_mixed_language_still_skip(source):
    tr = translator("unused")
    prepared = prepare_input(UserRequest(session_id="S", message=source), ENABLED, tr)
    assert not prepared.translation_attempted and prepared.message == source
    tr.translate.assert_not_called()


def test_sentence_initial_capital_typo_is_corrected_without_mutating_request():
    request = UserRequest(session_id="S", message="Cho mik quán yên tĩn xíu")
    before = deepcopy(request.model_dump())
    result = process_user_request(request, config=ConversationConfig())
    assert result.metadata.parsed_message == "Cho mình quán yên tĩnh xíu"
    assert result.preference_update == PreferenceUpdate(add_semantic_preferences=["quiet"])
    assert request.model_dump() == before


@pytest.mark.parametrize("message,results", [
    ('Tìm quán "Cho mik"', []), ('"Cho mik quán yên tĩn xíu"', []),
    ("Tìm quán Cho Mik", []),
    ("Cho mik quán yên tĩn xíu", [{"rank": 1, "restaurant_id": "R/01", "restaurant_name": "Cho mik"}]),
])
def test_initial_case_edit_preserves_quotes_and_supplied_names(message, results):
    request = UserRequest(session_id="S", message=message, previous_results=results)
    prepared = prepare_input(request, ConversationConfig())
    assert "Cho mik" in prepared.message or "Cho Mik" in prepared.message


@pytest.mark.parametrize("field,value", [
    ("transport_mode", "spaceship"), ("occasion", "chat"), ("meal_time", "unknown_time"),
])
@pytest.mark.parametrize("replacement", [False, True])
def test_known_context_fields_reject_unapproved_vocabulary(field, value, replacement):
    with pytest.raises(ValidationError):
        PreferenceUpdate(**({"set_values": {"context": {field: value}}} if replacement
                            else {"context_updates": {field: value}}))


def test_custom_context_food_and_semantics_remain_open():
    update = PreferenceUpdate(set_values={"food": ["unknown dish"], "cuisine": ["Regional cuisine"]},
        add_semantic_preferences=["custom atmosphere"], context_updates={"custom_time": "unknown_time",
        "companions": ["custom group"], "transport_mode": "on foot", "meal_time": "late night"})
    state = process_user_request(UserRequest(session_id="S", message="unknown description"),
        MockProvider(callback=lambda **kw: update), config=ConversationConfig()).state
    assert state.food == ["unknown dish"] and state.semantic_preferences == ["custom atmosphere"]
    assert state.context == {"custom_time": "unknown_time", "companions": ["custom group"],
                             "transport_mode": "walking", "meal_time": "late_night"}


def test_dish_location_currency_and_reference_entities_restore_verbatim():
    request = UserRequest(session_id="S", message='Find bun cha near "Little Tokyo" under USD 100',
        previous_results=[{"rank": 2, "restaurant_id": "R/02", "menu_item_id": "M:02", "restaurant_name": "Little Tokyo"}],
        current_state=UserPreferenceState(session_id="S", food=["phở"]), form={"budget_max": 90000})
    before = request.model_dump()
    tr = translator("Tìm AI2KEEP0X gần AI2KEEP1X dưới AI2KEEP2X")
    prepared = prepare_input(request, ENABLED, tr)
    assert prepared.translation_succeeded
    assert prepared.message == 'Tìm bun cha gần "Little Tokyo" dưới USD 100'
    assert request.model_dump() == before
