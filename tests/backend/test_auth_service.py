# Offline tests for AuthService, using the in-memory store and a fake clock
from datetime import datetime, timedelta, timezone

import pytest

from backend.adapters.auth_memory import InMemoryAuthStore
from backend.ports import (
    AccountLockedError,
    EmailTakenError,
    InvalidCredentialsError,
    WrongPasswordError,
)
from backend.services import passwords
from backend.services.auth_service import AuthConfig, AuthService, Registration

PASSWORD = "correct horse"


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta) -> None:
        self.now += timedelta(**delta)


@pytest.fixture(autouse=True)
def cheap_hashing(monkeypatch):
    # scrypt is slow on purpose; shrink the cost so this file stays fast
    monkeypatch.setattr(passwords, "_N", 2**4)
    monkeypatch.setattr(passwords, "_P", 1)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store():
    return InMemoryAuthStore()


@pytest.fixture
def auth(store, clock):
    return AuthService(store, store, AuthConfig(max_failures=3), clock)


def signup(auth, email="A@X.com", **over):
    data = dict(role="customer", full_name="A", email=email, password=PASSWORD)
    return auth.register(Registration(**{**data, **over}))


def test_register_normalizes_email_and_signs_in(auth, store):
    result = signup(auth)
    assert result.user.email == "a@x.com"
    assert auth.authenticate(result.token) == result.user
    assert result.token not in store._sessions  # only the hash is stored


def test_register_rejects_duplicate_email_in_any_case(auth):
    signup(auth, "a@x.com")
    with pytest.raises(EmailTakenError):
        signup(auth, "  A@X.COM ")


def test_register_rejects_bad_password_length(auth):
    with pytest.raises(ValueError):
        signup(auth, password="short")


def test_login_with_right_password(auth):
    first = signup(auth)
    second = auth.login("a@x.com", PASSWORD)
    assert second.user == first.user
    assert second.token != first.token  # a new session each time


def test_unknown_email_and_wrong_password_raise_the_same_error(auth):
    signup(auth)
    with pytest.raises(InvalidCredentialsError):
        auth.login("a@x.com", "wrong password")
    with pytest.raises(InvalidCredentialsError):
        auth.login("nobody@x.com", PASSWORD)


def test_account_locks_after_max_failures_then_unlocks(auth, clock):
    signup(auth)
    for _ in range(3):
        with pytest.raises(InvalidCredentialsError):
            auth.login("a@x.com", "wrong password")
    with pytest.raises(AccountLockedError):  # even the right password is refused
        auth.login("a@x.com", PASSWORD)

    clock.advance(minutes=16)
    assert auth.login("a@x.com", PASSWORD).user.email == "a@x.com"


def test_successful_login_resets_the_failure_counter(auth):
    signup(auth)
    for _ in range(2):
        with pytest.raises(InvalidCredentialsError):
            auth.login("a@x.com", "wrong password")
    auth.login("a@x.com", PASSWORD)
    for _ in range(2):  # would be the 3rd and 4th failure without the reset
        with pytest.raises(InvalidCredentialsError):
            auth.login("a@x.com", "wrong password")


def test_login_upgrades_an_old_hash(auth, store, monkeypatch):
    signup(auth)
    monkeypatch.setattr(passwords, "_N", 2**5)  # pretend the cost was raised later
    auth.login("a@x.com", PASSWORD)
    assert not passwords.needs_rehash(store.get_credentials("a@x.com").password_hash)


def test_authenticate_ignores_missing_unknown_and_expired_tokens(auth, clock):
    result = signup(auth)
    assert auth.authenticate(None) is None
    assert auth.authenticate("garbage") is None
    clock.advance(days=7, seconds=1)
    assert auth.authenticate(result.token) is None


def test_active_session_slides_forward(auth, clock):
    result = signup(auth)
    clock.advance(days=6)
    assert auth.authenticate(result.token) is not None  # touches: expiry moves to day 13
    clock.advance(days=2)  # day 8: dead without the touch
    assert auth.authenticate(result.token) is not None


def test_logout_kills_the_session_and_is_idempotent(auth):
    result = signup(auth)
    auth.logout(result.token)
    assert auth.authenticate(result.token) is None
    auth.logout(result.token)
    auth.logout(None)


def test_change_password_rotates_and_revokes_everything(auth):
    here = signup(auth)
    elsewhere = auth.login("a@x.com", PASSWORD)

    fresh = auth.change_password(here.user, PASSWORD, "brand new pass")

    assert auth.authenticate(here.token) is None
    assert auth.authenticate(elsewhere.token) is None
    assert auth.authenticate(fresh.token) == here.user
    assert auth.login("a@x.com", "brand new pass")
    with pytest.raises(InvalidCredentialsError):
        auth.login("a@x.com", PASSWORD)


def test_change_password_with_wrong_current_password(auth):
    result = signup(auth)
    with pytest.raises(WrongPasswordError):
        auth.change_password(result.user, "not my password", "brand new pass")
    assert auth.login("a@x.com", PASSWORD)  # unchanged


def test_customer_cannot_gain_a_shop_name(auth):
    user = signup(auth, shop_name="Phở Thìn").user
    assert user.shop_name is None
    updated = auth.update_profile(user, full_name=" B ", phone=" ", shop_name="Quán X")
    assert (updated.full_name, updated.phone, updated.shop_name) == ("B", None, None)


def test_sign_in_sweeps_expired_sessions(store, clock):
    auth = AuthService(store, store, AuthConfig(session_ttl=timedelta(hours=1)), clock)
    signup(auth, email="a@x.com")
    clock.advance(hours=2)  # the first session is now expired

    signup(auth, email="b@x.com")  # opening a session sweeps

    assert store.delete_expired_sessions(now=clock.now) == 0


def test_sweep_runs_at_most_once_per_interval(store, clock):
    config = AuthConfig(session_ttl=timedelta(minutes=10), cleanup_every=timedelta(hours=1))
    auth = AuthService(store, store, config, clock)
    signup(auth, email="a@x.com")  # the first sign-in sweeps, nothing to delete yet
    clock.advance(minutes=30)  # a's session is expired but the sweep is throttled

    signup(auth, email="b@x.com")

    assert store.delete_expired_sessions(now=clock.now) == 1  # a's row was still there


def test_a_failing_sweep_does_not_fail_the_sign_in(clock):
    class BrokenSweep(InMemoryAuthStore):
        def delete_expired_sessions(self, *, now):
            raise RuntimeError("database hiccup")

    broken = BrokenSweep()
    auth = AuthService(broken, broken, AuthConfig(), clock)

    result = signup(auth)

    assert auth.authenticate(result.token) == result.user