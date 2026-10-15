"""Contextual unitless VND after LLM interpretation, with existing safety intact."""
from decimal import Decimal
from unittest.mock import Mock

import pytest

from common.schemas import PreferenceUpdate, UserPreferenceState
from conversation.grounding import quantities, validate_numeric
from test_llm_first import run, turn


@pytest.mark.parametrize('message,food,amount', [
    ('tìm phở dưới 100000', 'phở', 100000),
    ('giảm ngân sách xuống 80000', None, 80000),
    ('giảm xuống dưới 150000', None, 150000),
    ('find fried chicken under 100000', 'fried chicken', 100000),
    ('budget below 150000', None, 150000),
    ('tìm phở dưới 100k', 'phở', 100000),
    ('tìm phở dưới 100.000đ', 'phở', 100000),
    ('tìm phở dưới 100000 VND', 'phở', 100000),
    ('budget below one hundred thousand VND', None, 100000),
    ('budget below 150,000', None, 150000),
    ('tìm phở dưới 100.000', 'phở', 100000),
    ('make it cheaper, budget below 80000', None, 80000),
    ('tìm phở dưới 100000, trong 3km', 'phở', 100000),
    ('find fried chicken under 100000.', 'fried chicken', 100000),
])
def test_grounded_amount_reaches_state_once_without_rule_first(monkeypatch, message, food, amount):
    monkeypatch.setattr('conversation.rule_parser.parse_by_rules_detailed', Mock(side_effect=AssertionError('No rule-first stage')))
    state = UserPreferenceState(session_id='S', food=['ramen'], location={'lat': 10.77, 'lon': 106.69},
        hard_constraints={'budget_max': 200000, 'max_distance_km': 3, 'allergens_excluded': ['milk', 'peanut']})
    delta = PreferenceUpdate(set_values={'food': [food]} if food else {}, add_hard_constraints={'budget_max': amount})
    result, primary, backup = run(monkeypatch, message, turn('refinement', delta), state=state)
    assert not result.metadata.clarification_required
    assert result.state.hard_constraints == {**state.hard_constraints, 'budget_max': amount}
    assert result.state.food == ([food] if food else state.food)
    assert result.state.location == state.location
    primary.interpret_turn.assert_called_once()
    backup.interpret_turn.assert_not_called()


@pytest.mark.parametrize('message', [
    '100000', 'tìm phở số 100000', 'order id 100000', 'tìm phở dưới 3',
    'ngân sách giữ nguyên, khoảng cách dưới 100000', 'budget below 100000 steps',
    'tìm phở dưới 100000 người', 'budget below 100000 USD', 'giảm số người xuống 80000',
    'budget below 100000 km', 'budget below 100000 phút', 'tìm phở dưới 100000 món',
    'ngân sách không phải dưới 100000', 'budget not below 100000',
    'ngân sách 10.77, 106.69', 'budget 100000-150000',
])
def test_arbitrary_numbers_and_other_dimensions_are_not_unitless_money(message):
    assert quantities(message, 'budget', food_search=True) == []
    with pytest.raises(ValueError):
        validate_numeric('budget_max', 100000, message, food_search=True)


@pytest.mark.parametrize('message,amount', [
    ('tìm phở dưới 100000', 100), ('budget below 150000', 150),
    ('giảm ngân sách xuống 80000', 800000),
])
def test_wrong_amount_rolls_back_and_preserves_constraints(monkeypatch, message, amount):
    delta = turn(delta=PreferenceUpdate(add_hard_constraints={'budget_max': amount}))
    state = UserPreferenceState(session_id='S', food=['phở'], hard_constraints={'budget_max': 200000, 'max_distance_km': 3})
    result, _, _ = run(monkeypatch, message, delta, delta, state=state)
    assert result.metadata.clarification_required and result.state == state


def test_budget_cannot_become_distance_or_minimum():
    assert {value for value, _ in quantities('budget below 100000', 'budget')} == {Decimal(100000)}
    with pytest.raises(ValueError):
        validate_numeric('max_distance_km', 100000, 'budget below 100000')
    with pytest.raises(ValueError):
        validate_numeric('budget_min', 100000, 'budget below 100000')
    with pytest.raises(ValueError):
        validate_numeric('budget_max', 100000, 'budget above 100000')


def test_reduction_alone_needs_monetary_or_food_context():
    assert quantities('giảm xuống dưới 150000', 'budget') == []
    assert quantities('reduce to 80000', 'budget') == []


def test_form_authority_and_provider_failover_remain_intact(monkeypatch):
    state = UserPreferenceState(session_id='S', food=['phở'], hard_constraints={'budget_max': 200000, 'max_distance_km': 3})
    delta = turn(delta=PreferenceUpdate(add_hard_constraints={'budget_max': 100000}))
    result, _, backup = run(monkeypatch, 'tìm phở dưới 100000', TimeoutError(), delta, state=state, form={'budget_max': 70000})
    assert result.state.hard_constraints == {'budget_max': 70000, 'max_distance_km': 3}
    assert result.state.food == ['phở'] and result.metadata.fallback_used
    backup.interpret_turn.assert_called_once()


def test_sequential_budget_refinements_keep_food_distance_and_allergies(monkeypatch):
    state = UserPreferenceState(session_id='S', food=['phở chay'], hard_constraints={
        'budget_max': 200000, 'max_distance_km': 3, 'vegetarian': True, 'allergens_excluded': ['milk']})
    for message, value in [('giảm ngân sách xuống 150000', 150000), ('giảm xuống dưới 80000', 80000)]:
        result, _, _ = run(monkeypatch, message, turn('refinement', PreferenceUpdate(add_hard_constraints={'budget_max': value})), state=state)
        assert not result.metadata.clarification_required
        assert result.state.food == state.food
        assert result.state.hard_constraints == {**state.hard_constraints, 'budget_max': value}
        state = result.state
