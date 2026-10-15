# Contract tests for the auth stores. The Postgres adapter will reuse them via the fixture
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import os
import pytest

from psycopg_pool import ConnectionPool
from backend.adapters.auth_pg import PostgresAuthStore
from backend.adapters.auth_memory import InMemoryAuthStore
from backend.ports import EmailTakenError, NewUser

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
LOCK = timedelta(minutes=15)


_TEST_DOMAIN = "@x.com"

def _wipe(pool) -> None:
    with pool.connection() as conn:
        conn.execute("DELETE FROM users WHERE email LIKE %s", (f"%{_TEST_DOMAIN}",))  # cascades

@pytest.fixture(params = ["memory", "postgres"])
def store(request):
    # Same contract tests run against every auth store implementation
    if request.param == "memory":
        yield InMemoryAuthStore()
        return
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    with ConnectionPool(url, min_size=1, max_size=8, open=False) as pool:
        _wipe(pool)  # clean slate before and after
        yield PostgresAuthStore(pool)
        _wipe(pool)


def new_user(email="a@x.com", **over) -> NewUser:
    fields = dict(email=email, password_hash="h", full_name="A", phone=None, role="customer", shop_name=None)
    return NewUser(**{**fields, **over})


def fail(store, user_id, times, now=NOW):
    for _ in range(times):
        store.record_failed_login(user_id, max_failures=3, lock_for=LOCK, now=now)


def test_create_then_lookup(store):
    user = store.create(new_user())
    found = store.get_credentials("a@x.com")
    assert found.user == user and found.password_hash == "h"
    assert store.get_credentials("nobody@x.com") is None


def test_duplicate_email_is_rejected(store):
    store.create(new_user())
    with pytest.raises(EmailTakenError):
        store.create(new_user())


@pytest.mark.parametrize("bad", [
    {"email": "A@x.com"},
    {"role": "admin"},
    {"role": "business", "shop_name": None},
    {"role": "business", "shop_name": "   "},
])
def test_store_enforces_the_same_rules_as_the_database(store, bad):
    with pytest.raises(ValueError):
        store.create(new_user(**bad))


def test_valid_business_account_is_accepted(store):
    user = store.create(new_user(role="business", shop_name="Phở Thìn"))
    assert user.role == "business"


def test_lock_after_max_failures_and_reset_when_it_expires(store):
    uid = store.create(new_user()).user_id
    fail(store, uid, 2)
    assert store.get_credentials("a@x.com").locked_until is None
    fail(store, uid, 1)
    assert store.get_credentials("a@x.com").locked_until == NOW + LOCK

    later = NOW + LOCK + timedelta(seconds=1)  # lock expired: one miss must not re-lock
    fail(store, uid, 1, now=later)
    creds = store.get_credentials("a@x.com")
    assert creds.failed_login_count == 1 and creds.locked_until is None


def test_successful_login_clears_the_counter(store):
    uid = store.create(new_user()).user_id
    fail(store, uid, 2)
    store.clear_failed_logins(uid)
    assert store.get_credentials("a@x.com").failed_login_count == 0


def test_session_lives_until_expiry(store):
    uid = store.create(new_user()).user_id
    store.create_session("tok", uid, now=NOW, expires_at=NOW + timedelta(days=7))
    assert store.get_session("tok", now=NOW).user.email == "a@x.com"
    assert store.get_session("tok", now=NOW + timedelta(days=7)) is None
    assert store.get_session("unknown", now=NOW) is None


def test_revoke_other_sessions_keeps_the_current_one(store):
    uid = store.create(new_user()).user_id
    for tok in ("t1", "t2", "t3"):
        store.create_session(tok, uid, now=NOW, expires_at=NOW + timedelta(days=1))
    store.delete_sessions_for_user(uid, keep="t2")
    assert [store.get_session(t, now=NOW) is not None for t in ("t1", "t2", "t3")] == [False, True, False]


def test_revoke_everything_when_no_session_is_kept(store):
    uid = store.create(new_user()).user_id
    for tok in ("t1", "t2"):
        store.create_session(tok, uid, now=NOW, expires_at=NOW + timedelta(days=1))
    store.delete_sessions_for_user(uid)  # keep=None
    assert [store.get_session(t, now=NOW) for t in ("t1", "t2")] == [None, None]


def test_delete_expired_counts_only_expired(store):
    uid = store.create(new_user()).user_id
    store.create_session("old", uid, now=NOW, expires_at=NOW + timedelta(hours=1))
    store.create_session("new", uid, now=NOW, expires_at=NOW + timedelta(days=1))
    assert store.delete_expired_sessions(now=NOW + timedelta(hours=2)) == 1


def test_concurrent_signups_with_one_email_yield_one_account(store):
    def try_create(_):
        try:
            store.create(new_user())
            return True
        except EmailTakenError:
            return False

    with ThreadPoolExecutor(20) as pool:
        results = list(pool.map(try_create, range(20)))
    assert results.count(True) == 1