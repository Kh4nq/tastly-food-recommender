"""Read-only homepage catalog query; no AI pipeline or preference session writes."""
from psycopg.rows import dict_row

from database.connection import get_pool


def nearby_menu_items(lat: float, lon: float, radius_km: float) -> list[dict]:
    with get_pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                WITH nearby AS MATERIALIZED (
                    SELECT r.*,
                        6371.0088 * acos(least(1.0, greatest(-1.0,
                            sin(radians(%(lat)s)) * sin(radians(r.latitude))
                            + cos(radians(%(lat)s)) * cos(radians(r.latitude))
                            * cos(radians(r.longitude - %(lon)s))
                        ))) AS distance_km
                    FROM restaurants r
                    WHERE r.is_recommendable
                        AND r.latitude BETWEEN -90 AND 90
                        AND r.longitude BETWEEN -180 AND 180
                        AND nullif(trim(r.name), '') IS NOT NULL
                ), places AS (
                    SELECT * FROM nearby
                    WHERE distance_km <= %(radius)s
                        AND EXISTS (
                            SELECT 1 FROM menu_items m JOIN dishes d ON d.dish_id = m.dish_id
                            WHERE m.food_place_id = nearby.food_place_id
                                AND coalesce(to_jsonb(d)->>'item_kind', 'food') = 'food'
                                AND nullif(trim(d.dish_name), '') IS NOT NULL
                        )
                    ORDER BY distance_km, food_place_id
                    LIMIT 200
                )
                SELECT p.food_place_id AS restaurant_id, p.name AS restaurant_name,
                    p.latitude, p.longitude, p.full_address AS address,
                    p.commune_name AS area, p.distance_km,
                    to_jsonb(p)->'rating' AS rating,
                    to_jsonb(p)->'review_count' AS review_count,
                    coalesce(menu.image_url, to_jsonb(p)->>'image_url') AS image_url,
                    menu.menu_item_id, menu.dish_id, menu.dish_name, menu.category,
                    menu.price, menu.price_is_verified, menu.is_synthetic
                FROM places p
                CROSS JOIN LATERAL (
                    SELECT m.menu_item_id, d.dish_id, d.dish_name,
                        d.primary_category AS category, m.price_vnd AS price,
                        m.price_is_verified, m.is_synthetic,
                        coalesce(to_jsonb(m)->>'image_url', to_jsonb(d)->>'image_url') AS image_url
                    FROM menu_items m JOIN dishes d ON d.dish_id = m.dish_id
                    WHERE m.food_place_id = p.food_place_id
                        AND coalesce(to_jsonb(d)->>'item_kind', 'food') = 'food'
                        AND nullif(trim(d.dish_name), '') IS NOT NULL
                    ORDER BY m.price_is_verified DESC, m.price_vnd, d.dish_name, m.menu_item_id
                    LIMIT 12
                ) menu
                """,
                {"lat": lat, "lon": lon, "radius": radius_km},
            )
            return list(cursor.fetchall())
