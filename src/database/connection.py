from __future__ import annotations

import os

from psycopg_pool import ConnectionPool


_pool: ConnectionPool | None = None


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is required. "
            "Set it before starting the backend."
        )

    return database_url


def get_pool() -> ConnectionPool:
    global _pool

    if _pool is None:
        _pool = ConnectionPool(
            conninfo=get_database_url(),
            min_size=1,
            max_size=10,
            timeout=10,
            open=True,
        )

    return _pool


def close_pool() -> None:
    global _pool

    if _pool is not None:
        _pool.close()
        _pool = None
