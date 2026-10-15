import pandas as pd
import pytest
from pydantic import ValidationError

from common.schemas import UserFormInput, UserRequest, UserPreferenceState
from conversation.parser import parse_user_input
from conversation.state_manager import update_state
from retrieval.hard_filter import filter_candidates
from scripts.update_serving_taxonomy import classify_dish, describe_space


@pytest.mark.parametrize('name,category,expected', [
    ('Phở bò', 'noodle', ('food', 'broth')),
    ('Phở cuốn', 'noodle', ('food', 'dry')),
    ('Hủ tiếu khô', 'noodle', ('food', 'dry')),
    ('Hủ tiếu', 'noodle', ('food', 'unknown')),
    ('Bún bò Huế', 'noodle', ('food', 'broth')),
    ('Trà sữa', 'beverage', ('beverage', 'not_applicable')),
    ('Canh rau', 'soup', ('food', 'soup')),
    ('Lẩu nấm', 'hotpot', ('food', 'hotpot')),
    ('Bò kho', 'main_dish', ('food', 'unknown')),
])
def test_serving_classification(name, category, expected):
    assert classify_dish({'dish_name': name, 'primary_category': category})[:2] == expected


def test_wet_food_request_never_retrieves_drinks():
    request = UserRequest(session_id='test', message='tôi muốn ăn món nước')
    state = update_state(UserPreferenceState(session_id='test'), parse_user_input(request), 'test')
    assert state.hard_constraints['item_kind'] == 'food'
    assert state.hard_constraints['serving_style'] == ['broth', 'soup']
    places = pd.DataFrame({'food_place_id': ['r'], 'latitude': [10.0], 'longitude': [106.0]})
    dishes = pd.DataFrame({'dish_id': ['pho', 'tea', 'dry', 'unknown'], 'is_vegetarian': [False]*4,
                          'item_kind': ['food', 'beverage', 'food', 'food'],
                          'serving_style': ['broth', 'not_applicable', 'dry', 'unknown']})
    menus = pd.DataFrame({'menu_item_id': ['a', 'b', 'c', 'd'], 'food_place_id': ['r']*4,
                         'dish_id': dishes.dish_id, 'price_vnd': [30000]*4})
    assert filter_candidates(places, dishes, menus, state.model_dump()).dish_id.tolist() == ['pho']
    drink_request = UserRequest(session_id='test', message='tôi muốn đồ uống', current_state=state)
    drink_state = update_state(state, parse_user_input(drink_request), 'test')
    assert drink_state.hard_constraints['item_kind'] == 'beverage'
    assert 'serving_style' not in drink_state.hard_constraints
    assert filter_candidates(places, dishes, menus, drink_state.model_dump()).dish_id.tolist() == ['tea']


def test_form_overrides_message_and_rejects_unknown_style():
    request = UserRequest(session_id='t', message='món nước', form=UserFormInput(item_kind='beverage'))
    update = parse_user_input(request)
    assert update.add_hard_constraints['item_kind'] == 'beverage'
    assert 'serving_style' not in update.add_hard_constraints
    with pytest.raises(ValidationError):
        UserFormInput(serving_style=['liquid'])


def test_last_explicit_serving_request_wins():
    update = parse_user_input(UserRequest(session_id='t', message='đồ uống, sau đó món nước'))
    assert update.add_hard_constraints['item_kind'] == 'food'
    assert update.add_hard_constraints['serving_style'] == ['broth', 'soup']
    assert 'hard_constraints.serving_style' not in update.remove_preferences


def test_space_description_only_uses_existing_profile_attributes():
    description, tags = describe_space({'quiet': True, 'wifi': False, 'capacity': 20})
    assert 'yên tĩnh' in description and '20' in description
    assert 'Wi-Fi' not in description and 'luxury' not in tags
