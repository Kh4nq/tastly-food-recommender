from __future__ import annotations

from typing import Any, Sequence

from psycopg.rows import dict_row

from .connection import get_pool


def get_restaurant_by_id(
    food_place_id: str,
) -> dict[str, Any] | None:
    with get_pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM get_restaurant_by_id(%s)
                """,
                (food_place_id,),
            )
            return cur.fetchone()


def get_restaurant_menu(
    food_place_id: str,
) -> list[dict[str, Any]]:
    with get_pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM get_restaurant_menu(%s)
                """,
                (food_place_id,),
            )
            return list(cur.fetchall())


def get_menu_items_by_ids(
    menu_item_ids: Sequence[str],
) -> list[dict[str, Any]]:
    ids = list(menu_item_ids)

    if not ids:
        return []

    with get_pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM get_menu_items_by_ids(%s)
                """,
                (ids,),
            )

            rows = list(cur.fetchall())

    # PostgreSQL ANY() does not guarantee the same ordering
    # as the AI Candidate input. Restore that ordering here.
    position = {
        menu_item_id: index
        for index, menu_item_id in enumerate(ids)
    }

    rows.sort(
        key=lambda row: position.get(
            row["menu_item_id"],
            len(position),
        )
    )

    return rows
