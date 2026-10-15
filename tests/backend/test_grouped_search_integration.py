"""Offline HTTP E2E: AI2 state -> real retrieval/CatBoost -> grouped frontend contract."""
from functools import partial
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.adapters.ai2_conversation import Ai2ConversationAdapter
from backend.adapters.session_memory import InMemorySessionStore
from backend.api.deps import Services
from backend.api.presenter import DishPresenter
from backend.main import create_app
from backend.services.pipeline import RecommendationPipeline
from backend.services.search_service import SearchService
from common.schemas import PreferenceUpdate
from ranking import rank_candidates
from retrieval.retriever import retrieve_candidates, retrieve_map_places
from test_llm_first import turn
from test_retrieval_food_pools import engine


def test_ai2_retrieval_rank_group_without_postranking_llm_and_frontend_contract(monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER', 'openrouter_chain')
    e = engine()
    e.dishes = pd.concat([e.dishes, pd.DataFrame([
        dict(dish_id='tai', dish_name='Phở tái', is_vegetarian=False),
        dict(dish_id='tai-variant', dish_name='Phở bò tái', is_vegetarian=False),
    ])], ignore_index=True)
    e.menus = pd.concat([e.menus, pd.DataFrame([
        dict(menu_item_id='direct1', food_place_id='A', dish_id='tai', price_vnd=55000),
        dict(menu_item_id='direct2', food_place_id='A', dish_id='tai-variant', price_vnd=60000),
    ])], ignore_index=True)
    e.dish_vectors = np.vstack([e.dish_vectors, [[1., 0.], [1., 0.]]]).astype('float32')
    e.dish_ids = pd.DataFrame({'vector_row': range(5), 'dish_id': e.dishes.dish_id})
    delta = PreferenceUpdate(set_values={'food': ['phở tái']}, add_hard_constraints={'budget_max': 100000, 'max_distance_km': 3}, context_updates={'transport_mode': 'car'})
    interpretation = SimpleNamespace(interpret_turn=Mock(return_value=turn(delta=delta)), close=Mock())
    monkeypatch.setattr('conversation.llm_first.create_provider', lambda _: interpretation)
    # Old local configuration cannot re-enable retired post-ranking calls.
    monkeypatch.setenv('BACKEND_EXPLANATION_ENABLED', 'true')
    provider_call = Mock(side_effect=AssertionError('No provider calls after AI2'))
    monkeypatch.setattr('conversation.providers.openrouter_provider.urlopen', provider_call)
    retrieve = partial(retrieve_candidates, retriever=e)
    pipeline = RecommendationPipeline(retrieve, rank_candidates)
    sessions = InMemorySessionStore()
    service = SearchService(sessions, Ai2ConversationAdapter(), pipeline,
        partial(retrieve_map_places, retriever=e))
    rows = []
    for menu in e.menus.to_dict('records'):
        dish = e.dishes.set_index('dish_id').loc[menu['dish_id']]
        restaurant = e.restaurants.set_index('food_place_id').loc[menu['food_place_id']]
        rows.append(dict(menu_item_id=menu['menu_item_id'], dish_name=dish.dish_name, restaurant_name=restaurant['name'],
            price_vnd=menu['price_vnd'], is_vegetarian=bool(dish.is_vegetarian), latitude=restaurant.latitude, longitude=restaurant.longitude))
    presenter = DishPresenter(SimpleNamespace(get_menu_items_by_ids=lambda ids: [row for row in rows if row['menu_item_id'] in ids]))
    with TestClient(create_app(Services(service, presenter))) as client:
        body = client.post('/api/search', json={'message': 'Tôi muốn phở tái dưới 100000, đi xe hơi, tối đa 3km',
            'form': {'location': {'lat': 10.77, 'lon': 106.69}}, 'include_map_places': True}).json()
        assert body['named_food_query'] and not body['clarification_required']
        assert body['state']['food'] == ['phở tái'] and body['state']['context']['transport_mode'] == 'car'
        assert 'transport_mode' not in body['state']['hard_constraints']
        assert [r['restaurant_id'] for r in body['results']] == ['A', 'B']
        primary, extra = body['results']
        assert primary['recommendation_group'] == 'primary' and primary['food_match'] > 0
        assert primary['menu_item_id'] in {'direct1', 'direct2'} and primary['restaurant_name'] == 'KFC'
        assert primary['explanation_source'] is None and primary['explanation'] is None
        assert {m['menu_item_id'] for m in primary['eligible_menu_items']} >= {'direct1', 'direct2'}
        assert all(m['price'] <= 100000 and m['distance_km'] <= 3 for r in body['results'] for m in r['eligible_menu_items'])
        assert all(m['dish_id'] != 'cake' for r in body['results'] for m in r['eligible_menu_items'])
        assert extra['recommendation_group'] == 'supplementary' and extra['food_match'] == 0 and extra['explanation'] is None
        assert len({p['id'] for p in body['map_places']}) == len(body['map_places']) == 2
        for r in body['results']:
            menu = e.menus.set_index('menu_item_id').loc[r['menu_item_id']]
            assert menu.food_place_id == r['restaurant_id'] and menu.dish_id == r['dish_id'] and menu.price_vnd == r['price_vnd']
            assert r['reason_features']['ranking_model'] == 'catboost_yetirank'
        again = client.post('/api/search', json={'preference_state': body['state'], 'include_map_places': True}).json()
        assert again['results'] == body['results']
        interpretation.interpret_turn.assert_called_once()
        provider_call.assert_not_called()
        interpretation.interpret_turn.return_value = turn('informational', reply='Phở thường có sợi dẹt, còn bún có sợi tròn.')
        chat = client.post('/api/search', json={'message': 'Phở khác bún như thế nào?'}).json()
        assert chat['intent'] == 'informational' and chat['results'] == [] and chat['state'] == body['state']
        provider_call.assert_not_called()
