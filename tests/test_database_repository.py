from __future__ import annotations

from unittest.mock import MagicMock, patch

from database import repository


def _mock_pool(rows):
    cursor = MagicMock()
    cursor.fetchone.return_value = rows[0] if rows else None
    cursor.fetchall.return_value = rows

    cursor_context = MagicMock()
    cursor_context.__enter__.return_value = cursor

    connection = MagicMock()
    connection.cursor.return_value = cursor_context

    connection_context = MagicMock()
    connection_context.__enter__.return_value = connection

    pool = MagicMock()
    pool.connection.return_value = connection_context

    return pool, cursor


def test_get_restaurant_by_id():
    expected = {
        "food_place_id": "osm:test",
        "name": "Test Restaurant",
    }

    pool, cursor = _mock_pool([expected])

    with patch.object(repository, "get_pool", return_value=pool):
        result = repository.get_restaurant_by_id("osm:test")

    assert result == expected

    args, _ = cursor.execute.call_args
    assert args[1] == ("osm:test",)


def test_get_restaurant_by_id_missing():
    pool, _ = _mock_pool([])

    with patch.object(repository, "get_pool", return_value=pool):
        result = repository.get_restaurant_by_id("missing")

    assert result is None


def test_get_restaurant_menu():
    expected = [
        {"menu_item_id": "menu:1"},
        {"menu_item_id": "menu:2"},
    ]

    pool, cursor = _mock_pool(expected)

    with patch.object(repository, "get_pool", return_value=pool):
        result = repository.get_restaurant_menu("osm:test")

    assert result == expected

    args, _ = cursor.execute.call_args
    assert args[1] == ("osm:test",)


def test_get_menu_items_by_ids_empty_does_not_query_database():
    with patch.object(repository, "get_pool") as get_pool:
        result = repository.get_menu_items_by_ids([])

    assert result == []
    get_pool.assert_not_called()


def test_get_menu_items_by_ids_restores_ai_ranking():
    database_rows = [
        {"menu_item_id": "menu:1"},
        {"menu_item_id": "menu:2"},
        {"menu_item_id": "menu:3"},
    ]

    pool, cursor = _mock_pool(database_rows)

    requested = [
        "menu:3",
        "menu:1",
        "menu:2",
    ]

    with patch.object(repository, "get_pool", return_value=pool):
        result = repository.get_menu_items_by_ids(requested)

    assert [
        row["menu_item_id"]
        for row in result
    ] == requested

    args, _ = cursor.execute.call_args
    assert args[1] == (requested,)
