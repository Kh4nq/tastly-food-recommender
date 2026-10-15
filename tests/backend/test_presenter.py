import logging

import pytest

from backend.api.presenter import DishPresenter
from backend.ports import CatalogUnavailableError
from common.schemas import RankedResult

# One row shaped like the get_menu_items_by_ids SQL function
ROW = {
    "menu_item_id": "M1",
    "food_place_id": "R1",
    "restaurant_name": "Pho Thin",
    "full_address": "13 Lo Duc",
    "latitude": 21.0,
    "longitude": 105.8,
    "dish_id": "D1",
    "dish_name": "Pho bo",
    "price_vnd": 55000,
    "price_is_verified": True,
    "is_vegetarian": False,
    "supported_cuisine": "vietnamese",
}


class FakeCatalog:
    def __init__(self, rows=(), error=None):
        self.rows, self.error, self.calls = list(rows), error, []

    def get_menu_items_by_ids(self, menu_item_ids):
        self.calls.append(list(menu_item_ids))
        if self.error:
            raise self.error
        return self.rows


def ranked(i, menu_item_id=None, **extra):
    return RankedResult(
        restaurant_id=f"R{i}", menu_item_id=menu_item_id, rank=i, score=1 / i, **extra
    )


def test_enriches_from_catalog_and_keeps_ids():
    [dish] = DishPresenter(FakeCatalog([ROW])).present([ranked(1, "M1", rating=4.5)])
    assert (dish.restaurant_id, dish.menu_item_id, dish.rank) == ("R1", "M1", 1)
    assert dish.restaurant_name == "Pho Thin" and dish.dish_name == "Pho bo"
    assert dish.price_vnd == 55000 and dish.location.lat == 21.0
    assert dish.rating == 4.5  # AI-only field survives
    assert dish.image_url is None and dish.review_count is None


def test_output_order_follows_ranking_not_database():
    rows = [{**ROW, "menu_item_id": "M2"}, ROW]  # database returns M2 first
    dishes = DishPresenter(FakeCatalog(rows)).present([ranked(1, "M1"), ranked(2, "M2")])
    assert [d.menu_item_id for d in dishes] == ["M1", "M2"]


def test_missing_row_falls_back_to_ai_fields():
    result = ranked(1, "M404", restaurant_name="AI name", price=40000)
    [dish] = DishPresenter(FakeCatalog([])).present([result])
    assert dish.restaurant_name == "AI name" and dish.price_vnd == 40000
    assert dish.address is None and dish.location is None


def test_catalog_failure_degrades_instead_of_failing(caplog):
    catalog = FakeCatalog(error=CatalogUnavailableError("db down"))
    with caplog.at_level(logging.WARNING):
        [dish] = DishPresenter(catalog).present([ranked(1, "M1", restaurant_name="AI name")])
    assert dish.restaurant_name == "AI name"
    assert "catalog unavailable" in caplog.text


def test_unexpected_catalog_errors_are_not_swallowed():
    with pytest.raises(RuntimeError):
        DishPresenter(FakeCatalog(error=RuntimeError("bug"))).present([ranked(1, "M1")])


def test_no_menu_item_ids_means_no_catalog_call():
    catalog = FakeCatalog([ROW])
    dishes = DishPresenter(catalog).present([ranked(1)])
    assert catalog.calls == [] and len(dishes) == 1