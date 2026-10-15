import pandas as pd

from retrieval.retriever import (
    BROWSE_MAX_DISHES_PER_RESTAURANT,
    Retriever,
    state_to_query,
)


def test_state_to_query_preserves_vietnamese_utf8():
    state = {
        "food": ["ph\u1edf"],
        "cuisine": ["Vi\u1ec7t Nam"],
        "soft_preferences": {},
        "semantic_preferences": [],
    }

    query = state_to_query(state)

    assert query == (
        "M\u00f3n \u0103n: ph\u1edf. "
        "\u1ea8m th\u1ef1c: Vi\u1ec7t Nam"
    )

    assert "M\u00c3" not in query
    assert "\u00e1\u00ba" not in query
    assert "\u00c4" not in query


def test_state_to_query_does_not_embed_numeric_constraints():
    state = {
        "food": ["ph\u1edf"],
        "cuisine": [],
        "soft_preferences": {},
        "semantic_preferences": [],
        "hard_constraints": {
            "budget_max": 100000,
            "max_distance_km": 5,
        },
    }

    query = state_to_query(state)

    assert "100000" not in query
    assert "5" not in query
    assert query == "M\u00f3n \u0103n: ph\u1edf"


def _browse_retriever():
    """Retriever over tiny in-memory tables: no data files, no embeddings."""
    retriever = Retriever.__new__(Retriever)
    retriever.restaurants = pd.DataFrame({
        "food_place_id": ["near", "far"],
        "latitude": [10.7770, 10.8000],
        "longitude": [106.7010, 106.7200],
    })
    retriever.dishes = pd.DataFrame({
        "dish_id": ["d1", "d2", "d3", "d4"],
        "dish_name": ["A", "B", "C", "D"],
        "is_vegetarian": ["false"] * 4,
    })
    retriever.menus = pd.DataFrame({
        "menu_item_id": ["m1", "m2", "m3", "m4", "m5"],
        "food_place_id": ["near", "near", "near", "far", "far"],
        "dish_id": ["d1", "d2", "d3", "d4", "d1"],
        "price_vnd": [30000, 40000, 50000, 20000, 60000],
    })
    return retriever


def test_browse_mode_caps_dishes_per_restaurant():
    state = {
        "location": {"lat": 10.7769, "lon": 106.7009},
        "food": [],
        "cuisine": [],
        "soft_preferences": {},
        "semantic_preferences": [],
    }

    frame = _browse_retriever().retrieve_frame(state, top_k=10)

    # One place must not fill the list, every restaurant still appears
    assert set(frame["restaurant_id"]) == {"near", "far"}
    per_restaurant = frame.groupby("restaurant_id").size()
    assert per_restaurant.max() <= BROWSE_MAX_DISHES_PER_RESTAURANT
    # Nearest restaurant first, and its cheapest dish is the one kept
    assert frame.iloc[0]["restaurant_id"] == "near"
    assert frame.iloc[0]["menu_item_id"] == "m1"
