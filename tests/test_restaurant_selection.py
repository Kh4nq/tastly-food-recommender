"""Restaurant Top-K and evidence precedence, independent of model internals."""
from unittest.mock import Mock

import pytest

from common.schemas import Candidate, RankedResult, UserPreferenceState
from pipeline.selection import select_restaurants
from backend.services.pipeline import RecommendationPipeline


def candidate(restaurant, menu, direct=True, score=1.):
    return Candidate(restaurant_id=restaurant, menu_item_id=menu, dish_id=menu,
        dish_name='Phở tái' if direct else 'Phở bò', price=50000,
        match_features={'food_match': 1. if direct else 0.,
                        'alternative_evidence': 'same_dish_family', 'test_score': score})


def ranked(candidates):
    return [RankedResult(**c.model_dump(include={'restaurant_id', 'menu_item_id', 'dish_id', 'dish_name', 'price'}),
        rank=i, score=c.match_features['test_score'], reason_features={'ranking_model': 'test'})
        for i, c in enumerate(candidates, 1)]


@pytest.mark.parametrize('direct,alternatives,expected', [(0, 12, (0, 10)), (3, 12, (3, 7)), (10, 12, (10, 0)), (15, 12, (10, 0)), (3, 2, (3, 2))])
def test_top_k_counts_restaurants_and_never_promotes_high_supplement_score(direct, alternatives, expected):
    pool = [candidate(f'P{i:02}', f'PM{i}', score=.1) for i in range(direct)] + [
        candidate(f'S{i:02}', f'SM{i}', False, score=100.) for i in range(alternatives)]
    out = select_restaurants(UserPreferenceState(session_id='s', food=['phở tái']), pool, ranked(pool), 10)
    groups = [r.reason_features['recommendation_group'] for r in out]
    assert groups == ['primary'] * expected[0] + ['supplementary'] * expected[1]
    assert len({r.restaurant_id for r in out}) == len(out)
    assert [r.rank for r in out] == list(range(1, len(out) + 1))


def test_representative_is_strongest_matching_menu_and_retains_other_evidence():
    pool = [candidate('R', 'm1', score=.5), candidate('R', 'm2', score=.7), candidate('R', 'm3', False, score=100)]
    original = ranked(pool)
    before = [r.model_dump() for r in original]
    out = select_restaurants(UserPreferenceState(session_id='s', food=['phở tái']), pool, original, 10)
    assert len(out) == 1 and out[0].menu_item_id == 'm2' and out[0].score == .7
    assert out[0].reason_features['candidate_rank'] == 2
    assert {r['menu_item_id'] for r in out[0].reason_features['eligible_menu_items']} == {'m1', 'm2', 'm3'}
    assert [r.model_dump() for r in original] == before


def test_ties_use_stable_ids_and_names_are_opaque():
    pool = [candidate('B', 'B2'), candidate('A', 'A2'), candidate('A', 'A1')]
    state = UserPreferenceState(session_id='s', food=['phở'])
    out = select_restaurants(state, pool, ranked(pool), 10)
    reverse = list(reversed(pool))
    again = select_restaurants(state, reverse, ranked(reverse), 10)
    assert [(r.restaurant_id, r.menu_item_id) for r in out] == [('A', 'A1'), ('B', 'B2')]
    assert [(r.restaurant_id, r.menu_item_id) for r in again] == [('A', 'A1'), ('B', 'B2')]


def test_unknown_zero_match_does_not_become_a_supplement():
    c = candidate('R', 'M', False)
    c.match_features.pop('alternative_evidence')
    assert select_restaurants(UserPreferenceState(session_id='s', food=['phở']), [c], ranked([c]), 10) == []


def test_general_search_is_not_supplementary():
    c = candidate('R', 'M', False)
    out = select_restaurants(UserPreferenceState(session_id='s'), [c], ranked([c]), 10)
    assert out[0].reason_features['recommendation_group'] == 'general'


def test_all_bounded_candidates_reach_ranker_before_restaurant_top_k():
    pool = [candidate('R1', f'M{i}', score=float(i)) for i in range(50)] + [candidate(f'R{i}', f'Other{i}') for i in range(2, 12)]
    retrieve = Mock(return_value=pool)
    rank = Mock(side_effect=lambda state, items, top_k: ranked(items))
    out = RecommendationPipeline(retrieve, rank).search(UserPreferenceState(session_id='s', food=['phở']), top_k=10)
    assert len(out) == 10 and len({r.restaurant_id for r in out}) == 10
    assert rank.call_args.kwargs['top_k'] == len(pool)
    assert retrieve.call_args.kwargs['top_k'] <= 1000


def test_duplicate_menu_identifiers_fail_loudly():
    pool = [candidate('A', 'M'), candidate('B', 'M')]
    with pytest.raises(ValueError, match='Duplicate'):
        select_restaurants(UserPreferenceState(session_id='s'), pool, ranked(pool), 10)
