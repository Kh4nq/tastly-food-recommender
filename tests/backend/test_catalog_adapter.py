import psycopg
import psycopg.errors
import psycopg_pool
import pytest

from backend.adapters.catalog_pg import PostgresCatalog
from backend.ports import CatalogUnavailableError


def raising(error):
    def fetch(menu_item_ids):
        raise error

    return fetch


def test_returns_rows_from_the_repository():
    rows = [{"menu_item_id": "M1"}]
    assert PostgresCatalog(fetch=lambda ids: rows).get_menu_items_by_ids(["M1"]) == rows


@pytest.mark.parametrize(
    "error",
    [
        psycopg.OperationalError("connection refused"),
        psycopg_pool.PoolTimeout("no free connection"),
        psycopg_pool.PoolClosed("pool closed"),
    ],
)
def test_connection_problems_become_catalog_unavailable(error):
    catalog = PostgresCatalog(fetch=raising(error))
    with pytest.raises(CatalogUnavailableError):
        catalog.get_menu_items_by_ids(["M1"])


@pytest.mark.parametrize(
    "error",
    [
        psycopg.errors.UndefinedFunction("function does not exist"),
        RuntimeError("DATABASE_URL is required"),
    ],
)
def test_bugs_and_misconfiguration_are_not_hidden(error):
    catalog = PostgresCatalog(fetch=raising(error))
    with pytest.raises(type(error)):
        catalog.get_menu_items_by_ids(["M1"])