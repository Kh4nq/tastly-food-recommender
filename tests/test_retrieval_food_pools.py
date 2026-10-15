"""Dish-only food evidence and bounded diversity; no model/network/artifact writes."""
import numpy as np
import pandas as pd
import pytest

from common.schemas import UserPreferenceState
from retrieval.food_matching import food_evidence, bounded_pools
from retrieval.profiles import UnsupportedConstraintError
from retrieval.retriever import Retriever, retrieve_candidates
from ranking import rank_candidates


@pytest.mark.parametrize('query,name,direct,related', [
    ('Phở chay', 'Phở chay', True, True), ('Phở chay', 'Phở nấm chay', True, True),
    ('Phở nấm chay', 'Phở chay nấm', True, True), ('Phở tái', 'Phở bò tái', True, True),
    ('Phở bò tái', 'Phở tái bò', True, True), ('pho tai', 'PHỞ BÒ TÁI', True, True),
    ('PHỞ', 'Phở gà', True, True), ('Phở tái', 'Phở bò', False, True),
    ('Phở tái', 'Phở gà', False, True), ('Phở', 'Bánh phô mai', False, False),
    ('Phở', 'Sinh tố', False, False), ('Phở chay', 'Gỏi cuốn chay', False, False),
    ('Phở', 'Salad phở bò', False, False), ('Phở', 'Pizza phở', False, False),
    ('Phở', 'Phô mai', False, False),
])
def test_dish_variants_and_misses(query, name, direct, related):
    score, family = food_evidence(name, [query])
    assert (score > 0) is direct and family is related
    if query.casefold() != name.casefold() and name not in ('PHỞ BÒ TÁI',):
        assert score < 1


def test_bounded_rounds_preserve_restaurants_and_both_pools():
    rows = [{'restaurant_id': 'prolific', 'menu_item_id': f'a{i}', 'food_match': 1.} for i in range(1000)]
    rows += [{'restaurant_id': f'p{i}', 'menu_item_id': f'p{i}', 'food_match': 1.} for i in range(15)]
    rows += [{'restaurant_id': f's{i}', 'menu_item_id': f's{i}', 'food_match': 0.} for i in range(15)]
    selected = bounded_pools(pd.DataFrame(rows), 40, True)
    assert len(selected) == 40 and selected.restaurant_id.nunique() == 31
    assert selected.loc[selected.food_match.gt(0)].restaurant_id.nunique() == 16
    assert selected.loc[selected.food_match.eq(0)].restaurant_id.nunique() == 15


def test_truncation_cannot_reclassify_a_matching_venue_as_supplementary():
    rows = [{'restaurant_id': f'P{i}', 'menu_item_id': f'direct{i}', 'food_match': 1.} for i in range(20)]
    rows += [{'restaurant_id': f'P{i}', 'menu_item_id': f'other{i}', 'food_match': 0.} for i in range(20)]
    rows += [{'restaurant_id': f'S{i}', 'menu_item_id': f's{i}', 'food_match': 0.} for i in range(5)]
    selected = bounded_pools(pd.DataFrame(rows), 10, True)
    direct_ids = set(selected.loc[selected.food_match.gt(0)].restaurant_id)
    assert set(selected.restaurant_id) <= direct_ids | {f'S{i}' for i in range(5)}


def engine():
    from types import SimpleNamespace
    e = Retriever.__new__(Retriever)
    e.restaurants = pd.DataFrame([
        dict(food_place_id='A', name='KFC', latitude=10.77, longitude=106.69),
        dict(food_place_id='B', name='Phở Hư Cấu', latitude=10.77, longitude=106.69),
        dict(food_place_id='far', name='Lotteria', latitude=11., longitude=107.),
    ])
    e.dishes = pd.DataFrame([
        dict(dish_id='pho', dish_name='Phở bò', is_vegetarian=False),
        dict(dish_id='veg', dish_name='Phở nấm chay', is_vegetarian=True),
        dict(dish_id='cake', dish_name='Bánh kem', is_vegetarian=True),
    ])
    e.menus = pd.DataFrame([dict(menu_item_id=f'{r}-{d}', food_place_id=r, dish_id=d, price_vnd=50000) for r in ('A', 'B', 'far') for d in ('pho', 'veg', 'cake')]
                             + [dict(menu_item_id='expensive', food_place_id='A', dish_id='veg', price_vnd=100001)])
    e.model = SimpleNamespace(encode=lambda *a, **kw: np.array([[1., 0.]], dtype='float32'))
    # Restaurant vectors intentionally disagree; their name-contaminated signal
    # must not affect either relevance or CatBoost input.
    e.restaurant_vectors = np.array([[1., 0.], [-1., 0.], [0., 1.]], dtype='float32')
    e.restaurant_ids = pd.DataFrame({'vector_row': [0, 1, 2], 'food_place_id': ['A', 'B', 'far']})
    e.dish_vectors = np.array([[1., 0.], [.8, .6], [1., 0.]], dtype='float32')
    e.dish_ids = pd.DataFrame({'vector_row': [0, 1, 2], 'dish_id': ['pho', 'veg', 'cake']})
    e.dish_weight = .75
    return e


def test_supplements_respect_hard_filters_and_ignore_brand_names():
    e = engine()
    state = UserPreferenceState(session_id='s', food=['phở tái chay'], location={'lat': 10.77, 'lon': 106.69},
        hard_constraints={'vegetarian': True, 'budget_max': 100000, 'max_distance_km': 3})
    out = retrieve_candidates(state, retriever=e)
    assert {c.menu_item_id for c in out} == {'A-veg', 'B-veg'}
    assert all(c.match_features['food_match'] == 0 and c.match_features['recommendation_group'] == 'supplementary' for c in out)
    assert all(c.match_features['restaurant_similarity'] == 0 for c in out)
    ranked = rank_candidates(state, out)
    assert ranked[0].score == pytest.approx(ranked[1].score)
    e.restaurants['name'] = ['McDonald\'s', 'KFC', 'Bánh Ngọt']
    again = retrieve_candidates(state, retriever=e)
    assert [(c.menu_item_id, c.match_features) for c in again] == [(c.menu_item_id, c.match_features) for c in out]
    assert [r.score for r in rank_candidates(state, again)] == [r.score for r in ranked]


def test_low_dish_similarity_cannot_use_restaurant_similarity_as_relevance():
    e = engine()
    e.dish_vectors[:] = [0., 1.]
    assert retrieve_candidates(UserPreferenceState(session_id='s', food=['phở tái']), retriever=e) == []


@pytest.mark.parametrize('hard', [{'allergens_excluded': ['milk']}, {'halal': True}])
def test_unknown_mandatory_constraints_still_fail_closed(hard):
    with pytest.raises(UnsupportedConstraintError):
        retrieve_candidates(UserPreferenceState(session_id='s', food=['phở'], hard_constraints=hard), retriever=engine())
