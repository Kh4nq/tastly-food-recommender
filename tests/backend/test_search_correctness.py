"""Authored offline search regressions: real AI2 -> AI1 -> CatBoost -> HTTP cards."""
from functools import partial
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.adapters.ai2_conversation import Ai2ConversationAdapter
from backend.adapters.session_memory import InMemorySessionStore
from backend.api.deps import Services
from backend.api.presenter import DishPresenter
from backend.main import create_app
from backend.services.pipeline import RecommendationPipeline
from backend.services.search_service import SearchService
from common.schemas import PreferenceUpdate, UserPreferenceState
from ranking import rank_candidates
from retrieval.retriever import Retriever, _add_food_match, retrieve_candidates, retrieve_map_places
from test_llm_first import run, turn


@pytest.fixture
def engine():
    engine = Retriever.__new__(Retriever)
    engine.restaurants = pd.DataFrame([
        dict(food_place_id='near', name='Fixture near', latitude=10.77, longitude=106.69),
        dict(food_place_id='far', name='Fixture far', latitude=11., longitude=107.),
    ])
    names = ['Phở chay', 'Phở nấm chay', 'Phở gà', 'Phở bò', 'Gỏi cuốn tôm', 'Gỏi cuốn chay', 'Cơm tấm sườn', 'Phở bò tái', 'Chén trứng', 'ramen']
    engine.dishes = pd.DataFrame([
        dict(dish_id=f'd{i}', dish_name=name, is_vegetarian=i in (0, 1, 5)) for i, name in enumerate(names)
    ])
    engine.menus = pd.DataFrame([
        dict(menu_item_id=f'm{i}', food_place_id='near', dish_id=f'd{i}', price_vnd=50000) for i in range(len(names))
    ] + [
        dict(menu_item_id='expensive', food_place_id='near', dish_id='d0', price_vnd=100001),
        dict(menu_item_id='far', food_place_id='far', dish_id='d0', price_vnd=50000),
    ])
    engine.model = SimpleNamespace(encode=Mock(return_value=np.array([[1., 0.]], dtype='float32')))
    engine.restaurant_vectors = np.array([[1., 0.], [1., 0.]], dtype='float32')
    engine.restaurant_ids = pd.DataFrame({'vector_row': [0, 1], 'food_place_id': ['near', 'far']})
    engine.dish_vectors = np.array([[1., 0.]] * len(names), dtype='float32')
    engine.dish_ids = pd.DataFrame({'vector_row': range(len(names)), 'dish_id': engine.dishes.dish_id})
    engine.dish_weight = .75
    return engine


def test_food_scores_do_not_call_qualified_names_exact(engine):
    frame = _add_food_match(engine.menus, engine.dishes, {'food': ['phở chay']})
    scores = frame.set_index('menu_item_id').food_match
    assert scores['m0'] == 1
    assert scores['m1'] == pytest.approx(.85)
    assert all(scores[f'm{i}'] == 0 for i in (2, 3, 4, 5, 6))


@pytest.mark.parametrize('message', ['Phở chay dưới 100k cách tôi 3km', 'Phở chay dưới 100k trong vòng 3km'])
def test_vegetarian_omission_repaired_and_matching_survives_top_k(monkeypatch, engine, message):
    delta = PreferenceUpdate(set_values={'food': ['phở chay']}, add_hard_constraints={'budget_max': 100000, 'max_distance_km': 3})
    result, _, _ = run(monkeypatch, message, turn(delta=delta), form={'location': {'lat': 10.77, 'lon': 106.69}})
    assert result.state.hard_constraints['vegetarian'] is True
    candidates = retrieve_candidates(result.state, retriever=engine, top_k=100)
    assert {c.menu_item_id for c in candidates} == {'m0', 'm1'}
    assert all(c.match_features['is_vegetarian'] and c.price <= 100000 and c.distance_km <= 3 for c in candidates)
    assert retrieve_candidates(result.state, retriever=engine, top_k=1)[0].menu_item_id == 'm0'
    # Real existing CatBoost; it can only rank eligible matching menu identities.
    ranked = rank_candidates(result.state, candidates)
    assert {r.menu_item_id for r in ranked} == {'m0', 'm1'}
    assert [r.model_dump() for r in ranked] == [r.model_dump() for r in rank_candidates(result.state, candidates)]
    assert all(r.reason_features['ranking_model'] == 'catboost_yetirank' for r in ranked)


def test_absent_dish_is_empty_before_encoder_or_ranker(engine):
    state = UserPreferenceState(session_id='S', food=['món không có trong dữ liệu'])
    rank = Mock()
    pipeline = RecommendationPipeline(partial(retrieve_candidates, retriever=engine), rank)
    assert pipeline.search(state) == []
    rank.assert_not_called()
    engine.model.encode.assert_not_called()


CAR_QUERY = 'ờm tôi đang mún ăn phở tái có chén trứng, tôi đi xe hơi, tối đa 10 km nhé'


@pytest.mark.parametrize('transport_scope', ['hard', 'context'])
def test_transport_repair_preserves_food_side_distance_and_allergies(monkeypatch, transport_scope):
    delta = PreferenceUpdate(set_values={'food': ['phở tái', 'chén trứng']}, add_hard_constraints={'max_distance_km': 10})
    if transport_scope == 'hard':
        delta.add_hard_constraints['transport_mode'] = 'xe hơi'
    else:
        delta.context_updates['transport_mode'] = 'car'
    state = UserPreferenceState(session_id='S', hard_constraints={'budget_max': 100000, 'allergens_excluded': ['milk']})
    result, primary, backup = run(monkeypatch, CAR_QUERY, turn(delta=delta), state=state)
    assert not result.metadata.clarification_required
    assert result.state.food == ['phở tái']
    assert result.state.context == {'transport_mode': 'car', 'requested_accompaniments': ['chén trứng']}
    assert result.state.hard_constraints == {'budget_max': 100000, 'allergens_excluded': ['milk'], 'max_distance_km': 10}
    primary.interpret_turn.assert_called_once()
    backup.interpret_turn.assert_not_called()


@pytest.mark.parametrize('message,delta', [
    ('Tìm phở, tôi đi bộ', PreferenceUpdate(set_values={'food': ['phở']}, add_hard_constraints={'transport_mode': 'car'})),
    ('Tìm phở', PreferenceUpdate(set_values={'food': ['phở']}, context_updates={'requested_accompaniments': ['chén trứng']})),
    ('Tìm phở tái, bắt buộc phải có chén trứng', PreferenceUpdate(set_values={'food': ['phở tái']})),
])
def test_unsupported_or_contradictory_provider_output_rolls_back(monkeypatch, message, delta):
    state = UserPreferenceState(session_id='S', food=['ramen'])
    result, _, _ = run(monkeypatch, message, turn(delta=delta), turn(delta=delta), state=state)
    assert result.metadata.clarification_required and result.state == state


def test_http_payload_preserves_real_menu_joins_and_reports_unverified_side(monkeypatch, engine):
    monkeypatch.setenv('LLM_PROVIDER', 'openrouter_chain')
    primary = SimpleNamespace(interpret_turn=Mock(return_value=turn(delta=PreferenceUpdate(
        set_values={'food': ['phở tái', 'chén trứng']}, add_hard_constraints={'transport_mode': 'car', 'max_distance_km': 10}))), close=Mock())
    monkeypatch.setattr('conversation.llm_first.create_provider', lambda _: primary)
    sessions = InMemorySessionStore()
    pipeline = RecommendationPipeline(partial(retrieve_candidates, retriever=engine), rank_candidates)
    rows = [dict(menu_item_id=f'm{i}', dish_name=row.dish_name, restaurant_name='Fixture near',
                 price_vnd=50000, latitude=10.77, longitude=106.69, is_vegetarian=bool(row.is_vegetarian))
            for i, row in engine.dishes.iterrows()]
    catalog = SimpleNamespace(get_menu_items_by_ids=lambda ids: [r for r in rows if r['menu_item_id'] in ids])
    maps = partial(retrieve_map_places, retriever=engine)
    services = Services(SearchService(sessions, Ai2ConversationAdapter(), pipeline, maps), DishPresenter(catalog))
    with TestClient(create_app(services)) as client:
        response = client.post('/api/search', json={'message': CAR_QUERY, 'form': {'location': {'lat': 10.77, 'lon': 106.69}}, 'include_map_places': True})
        assert response.status_code == 200
        body = response.json()
        assert not body['clarification_required']
        assert [(r['menu_item_id'], r['dish_id'], r['dish_name']) for r in body['results']] == [('m7', 'd7', 'Phở bò tái')]
        assert body['results'][0]['price_vnd'] == 50000
        assert body['results'][0]['location'] == dict(lat=10.77, lon=106.69)
        assert body['map_places'][0]['id'] == body['results'][0]['restaurant_id']
        assert any('chén trứng' in w and 'Chưa xác minh' in w for w in body['warnings'])
        assert any('địa lý' in w for w in body['warnings'])
        assert sessions.get(body['session_id']).state.context['transport_mode'] == 'car'


def test_genuinely_unsupported_hard_requirement_stays_strict(monkeypatch, engine):
    result, _, _ = run(monkeypatch, 'Tìm phở, bắt buộc có chứng nhận halal', turn(delta=PreferenceUpdate(
        set_values={'food': ['phở']}, add_hard_constraints={'chứng nhận halal': True})))
    from retrieval.profiles import UnsupportedConstraintError
    with pytest.raises(UnsupportedConstraintError):
        retrieve_candidates(result.state, retriever=engine)


def test_form_vegetarian_food_is_authoritative_even_without_diet_in_message(monkeypatch):
    state = UserPreferenceState(session_id='S', food=['ramen'], hard_constraints={'vegetarian': False})
    result, _, _ = run(monkeypatch, 'Tìm ramen', turn(delta=PreferenceUpdate(set_values={'food': ['ramen']})),
                       state=state, form={'food': 'phở chay'})
    assert not result.metadata.clarification_required
    assert result.state.food == ['phở chay'] and result.state.hard_constraints['vegetarian'] is True


def test_vegetarian_requirement_survives_generalized_model_food(monkeypatch):
    result, _, _ = run(monkeypatch, 'Phở chay dưới 100k', turn(delta=PreferenceUpdate(
        set_values={'food': ['phở']}, add_hard_constraints={'budget_max': 100000})))
    assert not result.metadata.clarification_required
    assert result.state.hard_constraints['vegetarian'] is True
