from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd
import psycopg


ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT / "data" / "processed"

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is required. Configure it in the environment."
    )

TABLES = {
    "restaurants": [
        "food_place_id",
        "name",
        "place_type",
        "cuisine",
        "latitude",
        "longitude",
        "house_number",
        "street",
        "commune_code",
        "commune_name",
        "province_code",
        "province_name",
        "full_address",
        "opening_hours",
        "phone",
        "website",
        "takeaway",
        "delivery",
        "outdoor_seating",
        "wheelchair",
        "is_recommendable",
        "source",
        "source_id",
        "normalized_cuisine",
        "cuisine_constraint_type",
        "cuisine_normalization_evidence",
        "supported_cuisine",
        "has_hard_cuisine_constraint",
        "supported_cuisine_evidence",
        "space_description", "space_tags", "space_source",
    ],
    "dishes": [
        "dish_id",
        "dish_name",
        "description",
        "dish_type",
        "serving_size",
        "cooking_time",
        "ingredients",
        "cooking_method",
        "dish_tags",
        "calories",
        "fat",
        "fiber",
        "sugar",
        "protein",
        "primary_category",
        "meal_role",
        "main_protein",
        "primary_cooking_style",
        "is_vegetarian",
        "source",
        "taxonomy_source",
        "cuisine_origin",
        "cuisine_confidence",
        "cuisine_evidence",
        "supported_cuisine",
        "is_hard_cuisine_eligible",
        "item_kind", "serving_style", "serving_style_evidence",
    ],
    "menu_items": [
        "menu_item_id",
        "food_place_id",
        "dish_id",
        "estimated_price_vnd",
        "is_synthetic",
        "simulation_method",
        "price_type",
        "price_vnd",
        "price_is_verified",
    ],
}
# Columns the V3 Parquet files do not carry. Filled only when the file lacks them
DEFAULTS = {
    "restaurants": {"space_description": None, "space_tags": None, "space_source": None},
    "dishes": {"item_kind": None, "serving_style": None, "serving_style_evidence": None},
    "menu_items": {"price_type": "VND"},
}


def normalize_value(value):
    if pd.isna(value):
        return None

    # Convert NumPy scalar types to normal Python values.
    if hasattr(value, "item"):
        return value.item()

    return value


def copy_dataframe(
    conn: psycopg.Connection,
    table: str,
    dataframe: pd.DataFrame,
    columns: list[str],
) -> None:
    missing = set(columns) - set(dataframe.columns)

    if missing:
        raise ValueError(
            f"{table}: missing required columns: {sorted(missing)}"
        )

    dataframe = dataframe[columns]

    column_sql = ", ".join(columns)

    with conn.cursor() as cur:
        with cur.copy(
            f"COPY {table} ({column_sql}) FROM STDIN"
        ) as copy:
            for row in dataframe.itertuples(index=False, name=None):
                copy.write_row(
                    tuple(normalize_value(value) for value in row)
                )


def load_table(
    conn: psycopg.Connection,
    table: str,
    parquet_path: Path,
) -> int:
    print(f"Loading {parquet_path} ...")

    df = pd.read_parquet(parquet_path)
    
     # A real column from the file always wins over the default
    df = df.assign(**{k: v for k, v in DEFAULTS.get(table, {}).items() if k not in df.columns})

    print(f"  rows: {len(df):,}")

    copy_dataframe(
        conn=conn,
        table=table,
        dataframe=df,
        columns=TABLES[table],
    )

    return len(df)


def expected_row_counts(processed_dir: Path = PROCESSED_DIR) -> dict[str, int]:
    """Accept each released dataset's counts; reject an inconsistent dataset card."""
    import pyarrow.parquet as pq
    expected = {
        table: pq.read_metadata(processed_dir / f"{table}.parquet").num_rows
        for table in TABLES
    }
    if any(count <= 0 for count in expected.values()):
        raise ValueError("Cannot seed an empty catalog")
    card_path = processed_dir / "ai1_dataset_card.json"
    if card_path.is_file():
        card = json.loads(card_path.read_text(encoding="utf-8"))
        for table, count in expected.items():
            key = "menus" if table == "menu_items" else table
            if card.get(key) != count:
                raise ValueError(f"Dataset card count mismatch: {table}")
    return expected


def main(*, if_empty: bool = False) -> None:
    expected = expected_row_counts()

    with psycopg.connect(DATABASE_URL) as conn:
        if if_empty:
            with conn.cursor() as cur:
                # A lock prevents another writer racing the empty check/seed.
                cur.execute("LOCK TABLE menu_items, dishes, restaurants IN ACCESS EXCLUSIVE MODE")
                for table in expected:
                    cur.execute(f"SELECT EXISTS (SELECT 1 FROM {table})")
                    if cur.fetchone()[0]:
                        print("Database already contains data; setup seed skipped (no rows replaced).")
                        return
        # Seed is intentionally replace-all so rerunning it is deterministic.
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE TABLE menu_items, dishes, restaurants;"
            )

        for table in ("restaurants", "dishes", "menu_items"):
            count = load_table(
                conn,
                table,
                PROCESSED_DIR / f"{table}.parquet",
            )

            if count != expected[table]:
                raise RuntimeError(
                    f"{table}: expected {expected[table]:,} rows, "
                    f"got {count:,}"
                )

        with conn.cursor() as cur:
            for table, expected_count in expected.items():
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                actual_count = cur.fetchone()[0]

                if actual_count != expected_count:
                    raise RuntimeError(
                        f"{table}: database contains "
                        f"{actual_count:,} rows; "
                        f"expected {expected_count:,}"
                    )

                print(
                    f"{table}: {actual_count:,} rows OK"
                )

        conn.commit()

    print("Database seed completed successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the local development database from processed V3 data.")
    parser.add_argument("--if-empty", action="store_true", help="Preserve any existing database rows (used by setup.ps1)")
    main(if_empty=parser.parse_args().if_empty)
