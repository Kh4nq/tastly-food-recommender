CREATE INDEX IF NOT EXISTS idx_menu_items_food_place_id
    ON menu_items(food_place_id);

CREATE INDEX IF NOT EXISTS idx_menu_items_dish_id
    ON menu_items(dish_id);

CREATE INDEX IF NOT EXISTS idx_restaurants_province_code
    ON restaurants(province_code);

CREATE INDEX IF NOT EXISTS idx_restaurants_recommendable
    ON restaurants(food_place_id)
    WHERE is_recommendable = TRUE;

CREATE INDEX IF NOT EXISTS idx_restaurants_supported_cuisine
    ON restaurants(supported_cuisine);

CREATE INDEX IF NOT EXISTS idx_dishes_supported_cuisine
    ON dishes(supported_cuisine);

CREATE INDEX IF NOT EXISTS idx_dishes_vegetarian
    ON dishes(dish_id)
    WHERE is_vegetarian = TRUE;

CREATE INDEX IF NOT EXISTS idx_menu_items_restaurant_price
    ON menu_items(food_place_id, price_vnd);

-- Revoke all sessions of one user; also speeds up the ON DELETE CASCADE
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user
    ON auth_sessions(user_id);

-- Cleanup job: DELETE ... WHERE expires_at < now()
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires
    ON auth_sessions(expires_at);