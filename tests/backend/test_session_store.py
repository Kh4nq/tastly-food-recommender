import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from psycopg_pool import ConnectionPool

from backend.adapters.session_memory import InMemorySessionStore
from backend.adapters.session_pg import PostgresSessionStore
from backend.ports import SessionConflictError
from common.schemas import UserPreferenceState


def make_state(food=None):
    return UserPreferenceState(session_id="S1", food=food or [])


@pytest.fixture(params=["memory", "postgres"])
def store(request):
    # Same contract tests run against every SessionStore implementation
    if request.param == "memory":
        yield InMemorySessionStore()
        return
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    with ConnectionPool(url, min_size=1, max_size=8, open=False) as pool:
        pg_store = PostgresSessionStore(pool)
        pg_store.delete("S1")  # clean slate before and after
        yield pg_store
        pg_store.delete("S1")


def test_unknown_session_returns_none(store):
    assert store.get("S1") is None


def test_save_new_session_starts_at_version_1(store):
    record = store.save("S1", make_state(["pho"]), expected_version=0)
    assert record.version == 1
    assert store.get("S1").state.food == ["pho"]


def test_each_save_bumps_version(store):
    store.save("S1", make_state(), expected_version=0)
    record = store.save("S1", make_state(["bun"]), expected_version=1)
    assert record.version == 2


def test_stale_version_is_rejected(store):
    store.save("S1", make_state(), expected_version=0)
    with pytest.raises(SessionConflictError):
        store.save("S1", make_state(), expected_version=0)


def test_new_session_with_wrong_version_is_rejected(store):
    with pytest.raises(SessionConflictError):
        store.save("S1", make_state(), expected_version=3)


def test_delete_removes_and_is_idempotent(store):
    store.save("S1", make_state(), expected_version=0)
    store.delete("S1")
    store.delete("S1")
    assert store.get("S1") is None


def test_returned_state_is_a_copy(store):
    store.save("S1", make_state(["pho"]), expected_version=0)
    store.get("S1").state.food.append("hacked")
    assert store.get("S1").state.food == ["pho"]


def test_state_survives_a_round_trip(store):
    state = UserPreferenceState(
        session_id="S1",
        food=["pho"],
        hard_constraints={"budget_max": 60000},
        context={"note": "tiếng Việt có dấu"},
    )
    store.save("S1", state, expected_version=0)
    assert store.get("S1").state == state


def test_concurrent_first_saves_exactly_one_wins(store):
    workers = 8
    start = Barrier(workers)  # release all threads at the same instant

    def attempt(_):
        start.wait()
        try:
            store.save("S1", make_state(), expected_version=0)
            return True
        except SessionConflictError:
            return False

    with ThreadPoolExecutor(workers) as pool:
        outcomes = list(pool.map(attempt, range(workers)))
    assert outcomes.count(True) == 1
    assert store.get("S1").version == 1