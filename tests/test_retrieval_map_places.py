from types import SimpleNamespace

import pandas as pd

from common.schemas import UserPreferenceState
from retrieval.retriever import retrieve_map_places


def engine():
    ids = [f'R{i}' for i in range(140)]
    return SimpleNamespace(
        restaurants=pd.DataFrame({'food_place_id': ids, 'name': ids,
                                  'latitude': [10.77] * 140, 'longitude': [106.7] * 140}),
        dishes=pd.DataFrame({'dish_id': ['pho', 'salad'], 'dish_name': ['Pho bo', 'Goi cuon'],
                             'is_vegetarian': [False, False]}),
        menus=pd.DataFrame([{'menu_item_id': f'{r}-{dish}', 'food_place_id': r,
                             'dish_id': dish, 'price_vnd': 40000 if i < 130 else 60000}
                            for i, r in enumerate(ids) for dish in ['pho', 'salad']]),
    )


def test_map_is_not_capped_and_deduplicates_restaurants():
    places = retrieve_map_places(UserPreferenceState(session_id='s'), retriever=engine())
    assert len(places) == 140
    assert len({p['id'] for p in places}) == 140


def test_map_applies_food_budget_and_exclusions():
    state = UserPreferenceState(session_id='s', food=['pho'], hard_constraints={'budget_max': 50000})
    places = retrieve_map_places(state, exclude=['R0'], retriever=engine())
    assert len(places) == 129
    assert all(p['dish'] == 'Pho bo' and p['id'] != 'R0' for p in places)
    assert all(p['price_vnd'] == 40000 and p['distance_km'] is None for p in places)


def test_map_does_not_replace_missing_food_with_unrelated_dishes():
    state = UserPreferenceState(session_id='s', food=['bun rieu'])
    assert retrieve_map_places(state, retriever=engine()) == []


def test_map_omits_missing_coordinates():
    source = engine()
    source.restaurants.loc[0, 'latitude'] = float('nan')
    places = retrieve_map_places(UserPreferenceState(session_id='s'), retriever=source)
    assert len(places) == 139
    assert all(p['id'] != 'R0' for p in places)
