import pandas as pd
import pytest

from retrieval.hard_filter import filter_candidates
from retrieval.geo_search import haversine_km


@pytest.fixture
def tables():
    places = pd.DataFrame({
        'food_place_id': ['near', 'far', 'closed'],
        'latitude': [21.0, 22.0, 21.0],
        'longitude': [105.0, 105.0, 105.0],
        'is_recommendable': [True, True, False],
    })

    dishes = pd.DataFrame({
        'dish_id': ['veg', 'meat', 'unknown'],
        'is_vegetarian': [True, False, None],
    })

    menus = pd.DataFrame({
        'menu_item_id': ['a', 'b', 'c', 'd', 'e'],
        'food_place_id': ['near', 'near', 'near', 'far', 'closed'],
        'dish_id': ['veg', 'meat', 'unknown', 'veg', 'veg'],
        'price_vnd': [50_000, 80_000, 40_000, 30_000, 10_000],
    })

    return places, dishes, menus


def test_budget_distance_vegetarian(tables):
    result = filter_candidates(
        *tables,
        {
            'location': [21.0, 105.0],
            'hard_constraints': {
                'budget_max': 60_000,
                'max_distance_km': 5,
                'vegetarian': True,
            },
        },
    )

    assert result['menu_item_id'].tolist() == ['a']
    assert result.iloc[0]['distance_km'] == pytest.approx(0)


def test_budget_only(tables):
    result = filter_candidates(
        *tables,
        {
            'budget_max_vnd': 45_000,
        },
    )

    # No dietary request => unknown vegetarian status is allowed.
    assert result['menu_item_id'].tolist() == ['c', 'd']


def test_missing_location(tables):
    with pytest.raises(ValueError, match='requires location'):
        filter_candidates(
            *tables,
            {
                'hard_constraints': {
                    'max_distance_km': 3,
                },
            },
        )


def test_unsupported_diet_fails_closed(tables):
    with pytest.raises(NotImplementedError, match='Unsupported'):
        filter_candidates(
            *tables,
            {
                'hard_constraints': {
                    'halal': True,
                },
            },
        )


def test_haversine():
    result = haversine_km(
        21,
        105,
        pd.Series([21, 22]),
        pd.Series([105, 105]),
    )

    assert result.iloc[0] == pytest.approx(0)
    assert 110 < result.iloc[1] < 112


@pytest.mark.parametrize(
    'constraint',
    [
        {'min_rating': 4.0},
        {'parking': True},
        {'wifi': True},
        {'air_conditioning': True},
        {'outdoor_seating': True},
        {'wheelchair_accessible': True},
        {'allergens_excluded': ['peanut']},
        {'max_travel_time_min': 20},
    ],
)
def test_unsupported_ai2_hard_constraints_fail_closed(tables, constraint):
    with pytest.raises(NotImplementedError, match='Unsupported'):
        filter_candidates(
            *tables,
            {
                'hard_constraints': constraint,
            },
        )


@pytest.mark.parametrize('price_column', ['price_vnd', 'estimated_price_vnd'])
def test_budget_range_includes_both_boundaries(tables, price_column):
    places, dishes, menus = tables
    menus = menus.copy().rename(columns={'price_vnd': price_column})
    menus[price_column] = [35_000, 50_000, 34_999, 50_001, 40_000]
    result = filter_candidates(places, dishes, menus, {
        'hard_constraints': {'budget_min': 35_000, 'budget_max': 50_000},
    })
    assert result['menu_item_id'].tolist() == ['a', 'b']
    assert result['price'].tolist() == [35_000, 50_000]


@pytest.mark.parametrize('state', [
    {'hard_constraints': {'budget_min': 50_000}},
    {'budget_min': 50_000},
])
def test_budget_min_only(tables, state):
    result = filter_candidates(*tables, state)
    assert result['menu_item_id'].tolist() == ['a', 'b']


@pytest.mark.parametrize('value', [-1, float('nan'), float('inf'), 'invalid'])
def test_invalid_budget_min(tables, value):
    with pytest.raises(ValueError, match='budget_min'):
        filter_candidates(*tables, {'hard_constraints': {'budget_min': value}})


def test_budget_min_zero(tables):
    result = filter_candidates(*tables, {'hard_constraints': {'budget_min': 0}})
    assert result['menu_item_id'].tolist() == ['a', 'b', 'c', 'd']


def test_inverted_budget_range(tables):
    with pytest.raises(ValueError, match='budget_min must be less than or equal'):
        filter_candidates(*tables, {
            'hard_constraints': {'budget_min': 50_000, 'budget_max': 35_000},
        })

def test_location_excludes_restaurant_without_coordinates(tables):
    places, dishes, menus = tables

    missing_coord = pd.DataFrame([
        {
            'food_place_id': 'missing-coord',
            'latitude': float('nan'),
            'longitude': float('nan'),
            'is_recommendable': True,
        }
    ])

    places = pd.concat(
        [places, missing_coord],
        ignore_index=True,
    )

    extra_menu = pd.DataFrame([
        {
            'menu_item_id': 'missing-menu',
            'food_place_id': 'missing-coord',
            'dish_id': 'veg',
            'price_vnd': 20_000,
        }
    ])

    menus = pd.concat(
        [menus, extra_menu],
        ignore_index=True,
    )

    result = filter_candidates(
        places,
        dishes,
        menus,
        {
            'location': [21.0, 105.0],
        },
    )

    assert 'missing-menu' not in result['menu_item_id'].tolist()
