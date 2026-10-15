-- ============================================================
-- MLAI Food - Backend query functions
-- ============================================================

-- 1. Get one restaurant.
CREATE OR REPLACE FUNCTION get_restaurant_by_id(
    p_food_place_id TEXT
)
RETURNS SETOF restaurants
LANGUAGE SQL
STABLE
AS $$
    SELECT *
    FROM restaurants
    WHERE food_place_id = p_food_place_id;
$$;


-- 2. Get one restaurant's menu.
CREATE OR REPLACE FUNCTION get_restaurant_menu(
    p_food_place_id TEXT
)
RETURNS TABLE (
    menu_item_id TEXT,
    dish_id TEXT,
    dish_name TEXT,
    price_vnd INTEGER,
    price_is_verified BOOLEAN,
    is_vegetarian BOOLEAN,
    supported_cuisine TEXT
)
LANGUAGE SQL
STABLE
AS $$
    SELECT
        m.menu_item_id,
        d.dish_id,
        d.dish_name,
        m.price_vnd,
        m.price_is_verified,
        d.is_vegetarian,
        d.supported_cuisine
    FROM menu_items AS m
    JOIN dishes AS d
        ON d.dish_id = m.dish_id
    WHERE m.food_place_id = p_food_place_id
    ORDER BY m.menu_item_id;
$$;


-- 3. Batch hydrate AI recommendation results.
-- Avoids N+1 queries when AI returns many candidates.
-- The return shape gains optional display columns; recreate within the setup transaction.
DROP FUNCTION IF EXISTS get_menu_items_by_ids(TEXT[]);
CREATE OR REPLACE FUNCTION get_menu_items_by_ids(
    p_menu_item_ids TEXT[]
)
RETURNS TABLE (
    menu_item_id TEXT,
    food_place_id TEXT,
    restaurant_name TEXT,
    full_address TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    dish_id TEXT,
    dish_name TEXT,
    price_vnd INTEGER,
    price_is_verified BOOLEAN,
    is_vegetarian BOOLEAN,
    supported_cuisine TEXT,
    item_kind TEXT,
    serving_style TEXT,
    space_description TEXT,
    space_tags JSONB,
    space_source TEXT
)
LANGUAGE SQL
STABLE
AS $$
    SELECT
        m.menu_item_id,
        r.food_place_id,
        r.name,
        r.full_address,
        r.latitude,
        r.longitude,
        d.dish_id,
        d.dish_name,
        m.price_vnd,
        m.price_is_verified,
        d.is_vegetarian,
        d.supported_cuisine,
        d.item_kind,
        d.serving_style,
        r.space_description,
        r.space_tags,
        r.space_source
    FROM menu_items AS m
    JOIN restaurants AS r
        ON r.food_place_id = m.food_place_id
    JOIN dishes AS d
        ON d.dish_id = m.dish_id
    WHERE m.menu_item_id = ANY(p_menu_item_ids);
$$;
