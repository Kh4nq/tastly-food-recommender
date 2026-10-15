# PostgreSQL Database

This directory contains the PostgreSQL schema and query functions used by
the MLAI Food backend.

## Tables

- `restaurants`: restaurant/place metadata.
- `dishes`: dish metadata and nutrition/cuisine information.
- `menu_items`: relationship between restaurants and dishes, including
  price metadata.

`menu_items.food_place_id` references `restaurants.food_place_id`.
`menu_items.dish_id` references `dishes.dish_id`.

PostgreSQL is optional; the direct AI2 -> AI1 -> AI3 pipeline does not require it.

## Local setup

From the repository root, `./setup.ps1 -WithDatabase` starts the existing Compose
service, waits for its healthcheck, applies schema/indexes/functions, and seeds an
empty database when processed V3 data is available. Reruns preserve existing rows.
Manual commands below remain available.

Copy the example environment configuration and configure local credentials.

Start PostgreSQL:

    docker compose up -d

Apply the schema:

    docker cp database/schema.sql mlai-food-postgres:/tmp/schema.sql
    docker exec mlai-food-postgres psql -v ON_ERROR_STOP=1 -U mlai -d mlai_food -f /tmp/schema.sql

Apply indexes:

    docker cp database/indexes.sql mlai-food-postgres:/tmp/indexes.sql
    docker exec mlai-food-postgres psql -v ON_ERROR_STOP=1 -U mlai -d mlai_food -f /tmp/indexes.sql

Apply backend query functions:

    docker cp database/procedures.sql mlai-food-postgres:/tmp/procedures.sql
    docker exec mlai-food-postgres psql -v ON_ERROR_STOP=1 -U mlai -d mlai_food -f /tmp/procedures.sql

## Python dependencies

Install the database dependency group:

    python -m pip install -e ".[db]"

Set `DATABASE_URL` in the backend environment.

Do not commit local database credentials.

## Seed data

The seed script loads the processed parquet artifacts:

- `data/processed/restaurants.parquet`
- `data/processed/dishes.parquet`
- `data/processed/menu_items.parquet`

Run:

    python scripts/seed_database.py

The seed operation is replace-all and is intended for development/demo
database initialization. Use `python scripts/seed_database.py --if-empty` to
preserve any existing rows; setup always uses this option.

Expected development dataset counts:

- restaurants: 26,025
- dishes: 4,000
- menu_items: 336,167

## Backend access

Use `src/database/repository.py` rather than opening a new PostgreSQL
connection for every request.

The database layer uses a connection pool and parameterized queries.

`get_menu_items_by_ids()` is intended for batch hydration of ranked AI
candidate IDs, avoiding one database query per recommendation.
