"""Location-aware homepage display selection, independent of AI ranking."""
import math
import unicodedata
from collections.abc import Callable


def _number(value, low: float, high: float) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) and low <= number <= high else None


def distance_km(lat: float, lon: float, other_lat: float, other_lon: float) -> float:
    phi, other_phi = math.radians(lat), math.radians(other_lat)
    value = math.sin((other_phi - phi) / 2) ** 2 + math.cos(phi) * math.cos(other_phi) * math.sin(math.radians(other_lon - lon) / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1, max(0, value))))


def _dish_key(name: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", name).casefold().split())


def get_today_recommendations(
    *, lat: float, lon: float, limit: int = 4, min_rating: float = 4.5,
    radius_km: float = 10, fetch: Callable[..., list[dict]],
) -> dict:
    candidates = []
    for row in fetch(lat, lon, radius_km):
        latitude = _number(row.get("latitude"), -90, 90)
        longitude = _number(row.get("longitude"), -180, 180)
        if latitude is None or longitude is None or not row.get("restaurant_id") or not row.get("dish_name"):
            continue
        distance = distance_km(lat, lon, latitude, longitude)
        if distance > radius_km:
            continue
        rating = _number(row.get("rating"), 0, 5)
        reviews = _number(row.get("review_count"), 0, 2**53 - 1)
        price = _number(row.get("price"), 0, 2**31 - 1)
        candidates.append({
            **row, "latitude": latitude, "longitude": longitude,
            "distance_km": distance, "rating": rating,
            "review_count": int(reviews) if reviews is not None and reviews.is_integer() else None,
            "price": int(price) if price is not None else None,
        })

    def tier(row):
        rating = row["rating"]
        return 0 if rating is not None and rating > min_rating else 1 if rating is not None and rating >= 4.3 else 2 if rating is not None else 3

    candidates.sort(key=lambda row: (
        tier(row), -(row["rating"] if row["rating"] is not None else -1),
        row["distance_km"], -(row["review_count"] or 0),
        row["restaurant_id"], row.get("menu_item_id") or "",
    ))
    selected, restaurants, dishes, items = [], set(), set(), set()
    # First keep both restaurant and dish variety. Relax variety only if necessary
    # to avoid blank slots when there are fewer than four distinct options.
    for distinct_restaurant, distinct_dish in [(True, True), (False, True), (True, False), (False, False)]:
        for row in candidates:
            dish = _dish_key(row["dish_name"])
            restaurant = _dish_key(row.get("restaurant_name") or row["restaurant_id"])
            item = (row["restaurant_id"], row.get("menu_item_id") or dish)
            if item in items or (distinct_restaurant and restaurant in restaurants) or (distinct_dish and dish in dishes):
                continue
            selected.append(row)
            restaurants.add(restaurant); dishes.add(dish); items.add(item)
            if len(selected) == limit:
                break
        if len(selected) == limit:
            break
    return {
        "items": selected,
        "radius_km": radius_km,
        "rating_fallback": any(row["rating"] is None or row["rating"] <= min_rating for row in selected),
        "unrated_included": any(row["rating"] is None for row in selected),
    }
