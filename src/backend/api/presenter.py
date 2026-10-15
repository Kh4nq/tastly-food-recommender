# Turn ranked AI result into frontend-ready DishResult, enriched from the catalog
import logging
from typing import Any

from backend.api.schemas import DishResult
from common.schemas import RankedResult , Location
from backend.ports import CatalogRepo, CatalogUnavailableError

log = logging.getLogger(__name__)

def to_dish_result (
    result : RankedResult,
    row : dict[str , Any] | None
) -> DishResult:
    row = row or {}
    has_point = row.get("latitude") is not None and row.get("longitude") is not None
    return DishResult (
        rank = result.rank,
        score = result.score,
        restaurant_id = result.restaurant_id,
        menu_item_id = result.menu_item_id,
        dish_id = result.dish_id,
        
        #catelog is the source of truth for display fields
        restaurant_name = row.get("restaurant_name") or result.restaurant_name,
        dish_name = row.get("dish_name") or result.dish_name,
        address = row.get("full_address"),
        location = Location (
            lat = row["latitude"] , 
            lon = row["longitude"]
        ) if has_point else None,
        price_vnd = row.get("price_vnd" , result.price),
        price_is_verified = row.get("price_is_verified"),
        distance_km = result.distance_km,
        rating = result.rating,
        is_vegetarian  = row.get("is_vegetarian"),
        cuisine = row.get("supported_cuisine"),
        item_kind = row.get('item_kind'),
        serving_style = row.get('serving_style'),
        space_description = row.get('space_description'),
        space_tags = row.get('space_tags') or [],
        space_source = row.get('space_source'),
        recommendation_group=result.reason_features.get('recommendation_group', 'general'),
        food_match=result.reason_features.get('food_match'),
        candidate_rank=result.reason_features.get('candidate_rank', result.rank),
        reason_features={k: v for k, v in result.reason_features.items() if k != 'eligible_menu_items'},
        eligible_menu_items=result.reason_features.get('eligible_menu_items', []),
    )
    
class DishPresenter:
    def __init__(self , catalog : CatalogRepo) -> None:
        self._catalog = catalog
        
    def present(self , results : list[RankedResult]) -> list[DishResult]:
        rows = self._fetch_rows([r.menu_item_id for r in results if r.menu_item_id])
        
        #output order follows the AI ranking, never the database order
        return [to_dish_result(r , rows.get(r.menu_item_id) if r.menu_item_id else None) for r in results]
    
    def _fetch_rows(self , menu_item_ids : list[str]) -> dict[str , dict[str , Any]]:
        if not menu_item_ids:
            return {}
        try:
            rows = self._catalog.get_menu_items_by_ids(menu_item_ids)
        except CatalogUnavailableError:
            log.warning("catalog unavailable; returning result without enrichment" , exc_info = True)
            return {}
        
        return {row["menu_item_id"] : row for row in rows}
