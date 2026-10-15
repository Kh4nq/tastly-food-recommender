# Adapter: PostgreSQL catalog behine CatalogRepo
from collections.abc import Callable, Sequence
from typing import Any

import psycopg

from database import repository
from backend.ports import CatalogUnavailableError

Fetch = Callable[[Sequence[str]] , list[dict[str , Any]]]

class PostgresCatalog:
    def __init__(self , fetch : Fetch = repository.get_menu_items_by_ids) -> None:
        #Injected so tests need no database
        self._fetch = fetch
        
    def get_menu_items_by_ids(self , menu_item_ids : Sequence[str]) -> list[dict[str , Any]]:
        try:
            return self._fetch(menu_item_ids)
        except psycopg.OperationalError as e:
            # Connection refused, server gone, pool timeout or closed pool
            # Bad SQL or misssing config are bugs, so they are no translated
            raise CatalogUnavailableError(str(e)) from e