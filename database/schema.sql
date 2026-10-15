BEGIN;

CREATE TABLE IF NOT EXISTS restaurants (
    food_place_id TEXT PRIMARY KEY,
    name TEXT,
    place_type TEXT NOT NULL,
    cuisine TEXT,

    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,

    house_number TEXT,
    street TEXT,
    commune_code DOUBLE PRECISION,
    commune_name TEXT,
    province_code INTEGER NOT NULL,
    province_name TEXT NOT NULL,
    full_address TEXT NOT NULL,

    opening_hours TEXT,
    phone TEXT,
    website TEXT,
    takeaway TEXT,
    delivery TEXT,
    outdoor_seating TEXT,
    wheelchair TEXT,

    is_recommendable BOOLEAN NOT NULL,

    source TEXT NOT NULL,
    source_id TEXT NOT NULL,

    normalized_cuisine TEXT NOT NULL,
    cuisine_constraint_type TEXT,
    cuisine_normalization_evidence TEXT,
    supported_cuisine TEXT NOT NULL,
    has_hard_cuisine_constraint BOOLEAN,
    supported_cuisine_evidence TEXT,

    CONSTRAINT chk_restaurant_latitude
        CHECK (latitude BETWEEN -90 AND 90),

    CONSTRAINT chk_restaurant_longitude
        CHECK (longitude BETWEEN -180 AND 180)
);

CREATE TABLE IF NOT EXISTS dishes (
    dish_id TEXT PRIMARY KEY,
    dish_name TEXT NOT NULL,
    description TEXT NOT NULL,
    dish_type TEXT NOT NULL,
    serving_size TEXT NOT NULL,
    cooking_time INTEGER NOT NULL,

    ingredients TEXT NOT NULL,
    cooking_method TEXT NOT NULL,
    dish_tags TEXT NOT NULL,

    calories INTEGER NOT NULL,
    -- Grams can be fractional; unknown nutrients stay NULL, never invented zero.
    fat DOUBLE PRECISION,
    fiber DOUBLE PRECISION,
    sugar DOUBLE PRECISION,
    protein DOUBLE PRECISION,

    primary_category TEXT NOT NULL,
    meal_role TEXT NOT NULL,
    main_protein TEXT NOT NULL,
    primary_cooking_style TEXT NOT NULL,

    is_vegetarian BOOLEAN NOT NULL,

    source TEXT NOT NULL,
    taxonomy_source TEXT NOT NULL,
    cuisine_origin TEXT NOT NULL,
    cuisine_confidence TEXT NOT NULL,
    cuisine_evidence TEXT NOT NULL,
    supported_cuisine TEXT NOT NULL,
    is_hard_cuisine_eligible BOOLEAN NOT NULL,

    CONSTRAINT chk_dish_cooking_time CHECK (cooking_time >= 0),
    CONSTRAINT chk_dish_calories CHECK (calories >= 0),
    CONSTRAINT chk_dish_fat CHECK (fat >= 0),
    CONSTRAINT chk_dish_fiber CHECK (fiber >= 0),
    CONSTRAINT chk_dish_sugar CHECK (sugar >= 0),
    CONSTRAINT chk_dish_protein CHECK (protein >= 0)
);

CREATE TABLE IF NOT EXISTS menu_items (
    menu_item_id TEXT PRIMARY KEY,
    food_place_id TEXT NOT NULL,
    dish_id TEXT NOT NULL,

    estimated_price_vnd INTEGER NOT NULL,
    is_synthetic BOOLEAN NOT NULL,
    simulation_method TEXT NOT NULL,
    price_type TEXT NOT NULL,
    price_vnd INTEGER NOT NULL,
    price_is_verified BOOLEAN NOT NULL,

    CONSTRAINT fk_menu_restaurant
        FOREIGN KEY (food_place_id)
        REFERENCES restaurants(food_place_id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,

    CONSTRAINT fk_menu_dish
        FOREIGN KEY (dish_id)
        REFERENCES dishes(dish_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    CONSTRAINT chk_estimated_price CHECK (estimated_price_vnd >= 0),
    CONSTRAINT chk_price CHECK (price_vnd >= 0)
);

-- Backend sessions: one row per anonymous visitor (src/backend/adapters/session_pg.py)
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    state JSONB NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Accounts (used by src/backend/adapters/user_pg.py)
CREATE TABLE IF NOT EXISTS users (
    user_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Stored lowercase and trimmed by the app; the CHECK below is the safety net
    email              TEXT NOT NULL,

    -- Format: scrypt$N$r$p$salt_hex$hash_hex (parameters travel with the hash)
    password_hash      TEXT NOT NULL,

    full_name          TEXT NOT NULL,
    phone              TEXT,
    role               TEXT NOT NULL,
    shop_name          TEXT,

    -- Brute-force protection lives here so every worker shares one counter
    failed_login_count INTEGER NOT NULL DEFAULT 0,
    locked_until       TIMESTAMPTZ,

    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_users_email UNIQUE (email),
    CONSTRAINT chk_users_email_lower CHECK (email = lower(email)),
    CONSTRAINT chk_users_role CHECK (role IN ('customer', 'business')),

    -- A business account must name its shop (NULL and blank are both rejected)
    CONSTRAINT chk_users_shop_name CHECK (
        role <> 'business' OR (shop_name IS NOT NULL AND btrim(shop_name) <> '')
    )
);

-- Login sessions: the cookie holds the token, the database holds only its SHA-256
CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash   TEXT PRIMARY KEY,
    user_id      UUID NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at   TIMESTAMPTZ NOT NULL
);

-- CREATE TABLE IF NOT EXISTS does not update an existing Kaggle database.
-- Keep old catalogs compatible with nullable/fractional nutrition metadata.
ALTER TABLE dishes
    ALTER COLUMN fat TYPE DOUBLE PRECISION USING fat::double precision,
    ALTER COLUMN fat DROP NOT NULL,
    ALTER COLUMN fiber TYPE DOUBLE PRECISION USING fiber::double precision,
    ALTER COLUMN fiber DROP NOT NULL,
    ALTER COLUMN sugar TYPE DOUBLE PRECISION USING sugar::double precision,
    ALTER COLUMN sugar DROP NOT NULL,
    ALTER COLUMN protein TYPE DOUBLE PRECISION USING protein::double precision,
    ALTER COLUMN protein DROP NOT NULL;

-- Optional serving taxonomy and generated display metadata; legacy rows remain valid.
ALTER TABLE dishes ADD COLUMN IF NOT EXISTS item_kind TEXT;
ALTER TABLE dishes ADD COLUMN IF NOT EXISTS serving_style TEXT;
ALTER TABLE dishes ADD COLUMN IF NOT EXISTS serving_style_evidence TEXT;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS space_description TEXT;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS space_tags JSONB;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS space_source TEXT;

COMMIT;
