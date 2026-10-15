from typing import Annotated
from collections.abc import Callable

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from backend.adapters.today_catalog import nearby_menu_items
from backend.services.today_recommendations import get_today_recommendations

router = APIRouter(prefix="/api/recommendations")


class TodayItem(BaseModel):
    restaurant_id: str
    restaurant_name: str
    menu_item_id: str
    dish_id: str
    dish_name: str
    image_url: str | None = None
    category: str
    rating: float | None = None
    review_count: int | None = None
    price: int | None = None
    price_is_verified: bool = False
    is_synthetic: bool = False
    latitude: float
    longitude: float
    distance_km: float
    area: str | None = None
    address: str | None = None


class TodayResponse(BaseModel):
    items: list[TodayItem]
    radius_km: float
    rating_fallback: bool
    unrated_included: bool


def get_today_catalog():
    return nearby_menu_items


@router.get("/today", response_model=TodayResponse)
def today(
    lat: Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)],
    lon: Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)],
    fetch: Annotated[Callable, Depends(get_today_catalog)],
    limit: Annotated[int, Query(ge=1, le=4)] = 4,
    min_rating: Annotated[float, Query(ge=4.3, le=5, allow_inf_nan=False)] = 4.5,
    radius_km: Annotated[float, Query(ge=1, le=20, allow_inf_nan=False)] = 10,
):
    # A plain def runs blocking database work in FastAPI's thread pool. This
    # endpoint never allocates/resets an anonymous food-search session.
    return get_today_recommendations(lat=lat, lon=lon, limit=limit, min_rating=min_rating, radius_km=radius_km, fetch=fetch)
