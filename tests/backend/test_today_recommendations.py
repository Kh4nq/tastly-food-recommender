import math

import pytest
from fastapi.testclient import TestClient

from backend.api.routes_recommendations import get_today_catalog
from backend.main import create_app
from backend.services.today_recommendations import get_today_recommendations


def item(rest, dish, *, lat=10.78, lon=106.68, rating=4.8, reviews=100, **overrides):
    return dict(restaurant_id=rest, restaurant_name=rest, menu_item_id=f"{rest}:{dish}",
                dish_id=dish, dish_name=dish, latitude=lat, longitude=lon, rating=rating,
                review_count=reviews, category="noodle", price=50000,
                price_is_verified=False, **overrides)


def select(rows, **kwargs):
    return get_today_recommendations(lat=10.78, lon=106.68, fetch=lambda *_: rows, **kwargs)


def test_rating_then_distance_then_reviews_without_district_restrictions():
    rows = [item("low", "a", rating=4.7), item("far", "b", lat=10.8),
            item("near", "c", reviews=50), item("more_reviews", "d", reviews=500)]
    result = select(rows)
    assert [row["restaurant_id"] for row in result["items"]] == ["more_reviews", "near", "far", "low"]
    assert result["rating_fallback"] is False


def test_relaxes_rating_to_43_before_lower_or_unknown():
    rows = [item("high", "a", rating=4.9), item("threshold", "b", rating=4.5),
            item("relaxed", "c", rating=4.3), item("lower", "d", rating=4.2),
            item("unknown", "e", rating=None)]
    result = select(rows)
    assert [row["restaurant_id"] for row in result["items"]] == ["high", "threshold", "relaxed", "lower"]
    assert result["rating_fallback"] is True
    assert result["unrated_included"] is False


def test_diversifies_restaurants_and_dishes_first():
    rows = [item("one", "pho"), item("one", "rice"), item("two", "pho"),
            item("two", "salad"), item("three", "noodles"), item("four", "bread")]
    result = select(rows)["items"]
    assert len(result) == 4
    assert len({row["restaurant_id"] for row in result}) == 4
    assert len({row["dish_name"] for row in result}) == 4


def test_unknown_ratings_stay_unknown_and_nearest_places_win():
    rows = [item("far", "pho", lat=10.8, rating=None, reviews=None),
            item("near", "rice", rating=None, reviews=None)]
    result = select(rows)
    assert [row["restaurant_id"] for row in result["items"]] == ["near", "far"]
    assert result["unrated_included"] is True
    assert all(row["rating"] is None and row["review_count"] is None for row in result["items"])


def test_duplicate_place_names_do_not_fill_the_preview_when_alternatives_exist():
    rows = [item("osm-1", "pho"), item("osm-2", "rice"), item("other", "salad"),
            item("third", "bread"), item("fourth", "soup")]
    rows[0]["restaurant_name"] = "Same cafe"
    rows[1]["restaurant_name"] = "  Same   cafe  "
    result = select(rows)["items"]
    assert len({" ".join(row["restaurant_name"].split()) for row in result}) == 4


def test_does_not_create_slots_when_data_is_sparse():
    row = item("only", "pho")
    assert len(select([row, row])["items"]) == 1
    assert select([])["items"] == []


def test_relaxes_diversity_to_fill_four_available_menu_items():
    rows = [item("only", dish) for dish in ["a", "b", "c", "d"]]
    assert len(select(rows)["items"]) == 4


@pytest.mark.parametrize("lat,lon", [(None, 106), (math.nan, 106), (91, 106), (10, math.inf), (True, 106), (21, 105)])
def test_invalid_or_out_of_radius_coordinates_are_excluded(lat, lon):
    assert select([item("bad", "a", lat=lat, lon=lon)])["items"] == []


def client_with(rows):
    app = create_app(services=object())
    app.dependency_overrides[get_today_catalog] = lambda: lambda *_: rows
    return TestClient(app, raise_server_exceptions=False)


def test_endpoint_is_read_only_and_returns_card_contract_without_session_cookie():
    client = client_with([item("one", "pho", rating=None, reviews=None)])
    response = client.get("/api/recommendations/today?lat=10.78&lon=106.68")
    assert response.status_code == 200
    assert "set-cookie" not in response.headers
    card = response.json()["items"][0]
    assert card["distance_km"] == 0
    assert card["rating"] is None and card["review_count"] is None
    assert card["price_is_verified"] is False
    assert card["restaurant_id"] == "one"


@pytest.mark.parametrize("query", ["", "lat=10&lon=181", "lat=nan&lon=106", "lat=10&lon=106&limit=5", "lat=10&lon=106&radius_km=100", "lat=10&lon=106&min_rating=nan"])
def test_endpoint_rejects_invalid_location_and_limits(query):
    assert client_with([]).get(f"/api/recommendations/today?{query}").status_code == 422
