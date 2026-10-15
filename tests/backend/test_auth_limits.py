# Offline tests for the abuse limits on /api/auth: no network, no database
import asyncio
import threading
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend.adapters.auth_memory import InMemoryAuthStore
from backend.api.deps import Services
from backend.gate import BusyError
from backend.limits import HashGate, RateLimitedError, RateLimiter
from backend.main import create_app
from backend.services import passwords
from backend.services.auth_service import AuthService
from backend.settings import Settings


@pytest.fixture(autouse=True)
def cheap_hashing(monkeypatch):
    monkeypatch.setattr(passwords, "_N", 2**4)  # scrypt is slow on purpose
    monkeypatch.setattr(passwords, "_P", 1)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def make_client(settings=None, **services_over):
    store = InMemoryAuthStore()
    # Search is not involved here, so its parts can be None
    services = Services(
        search_service=None, presenter=None, auth_service=AuthService(store, store), **services_over
    )
    return TestClient(create_app(services, settings))


def bad_login(client, **headers):
    return client.post(
        "/api/auth/login", json={"email": "no@x.com", "password": "whatever"}, headers=headers
    )


def error_code(response):
    return response.json()["error"]["code"]


# --- RateLimiter ---

def test_bucket_allows_a_burst_blocks_then_refills():
    clock = FakeClock()
    limiter = RateLimiter(burst=2, per_minute=60, clock=clock)  # 1 token per second
    limiter.hit("a")
    limiter.hit("a")
    with pytest.raises(RateLimitedError) as caught:
        limiter.hit("a")
    assert caught.value.retry_after == timedelta(seconds=1)
    limiter.hit("b")  # another IP is not affected
    clock.now += 1
    limiter.hit("a")  # one token came back


def test_idle_buckets_are_dropped_when_the_table_is_full(monkeypatch):
    from backend import limits

    monkeypatch.setattr(limits, "_MAX_KEYS", 3)
    clock = FakeClock()
    limiter = RateLimiter(burst=2, per_minute=60, clock=clock)
    for key in "abc":
        limiter.hit(key)
    clock.now += 10  # every bucket has refilled to full
    limiter.hit("d")  # 4th key pushes past the cap and triggers the cleanup
    assert set(limiter._buckets) == {"d"}


# --- HashGate ---

def test_hash_gate_says_busy_when_no_slot_frees_in_time():
    gate = HashGate(concurrency=1, queue_timeout_s=0.05)
    release = threading.Event()

    async def scenario():
        slow = asyncio.create_task(gate.run(release.wait))
        await asyncio.sleep(0.01)  # let it take the only slot
        with pytest.raises(BusyError):
            await gate.run(lambda: None)
        release.set()
        await slow

    asyncio.run(scenario())


def test_hash_gate_frees_the_slot_when_the_work_fails():
    gate = HashGate(concurrency=1, queue_timeout_s=0.05)

    def boom():
        raise ValueError("bad")

    async def scenario():
        for _ in range(3):  # a leaked slot would turn the 2nd call into BusyError
            with pytest.raises(ValueError):
                await gate.run(boom)

    asyncio.run(scenario())


# --- HTTP ---

def test_login_is_429_after_the_burst_with_retry_after():
    client = make_client(auth_limiter=RateLimiter(burst=2, per_minute=1))
    assert bad_login(client).status_code == 401
    assert bad_login(client).status_code == 401
    blocked = bad_login(client)
    assert blocked.status_code == 429 and error_code(blocked) == "rate_limited"
    assert int(blocked.headers["retry-after"]) >= 1


def test_register_shares_the_same_limit():
    client = make_client(auth_limiter=RateLimiter(burst=1, per_minute=1))
    first = client.post("/api/auth/register", json=dict(
        role="customer", full_name="An", email="an@x.com", password="correct horse"))
    assert first.status_code == 201
    second = client.post("/api/auth/register", json=dict(
        role="customer", full_name="Bo", email="bo@x.com", password="correct horse"))
    assert second.status_code == 429


def test_foreign_origin_is_403_but_allowed_or_missing_origin_passes():
    client = make_client()
    evil = bad_login(client, Origin="https://evil.example")
    assert evil.status_code == 403 and error_code(evil) == "forbidden_origin"
    assert bad_login(client, Origin="http://localhost:3000").status_code == 401  # past the guard
    assert bad_login(client).status_code == 401  # curl, tests: no Origin header


def test_a_blocked_origin_does_not_spend_a_rate_limit_token():
    client = make_client(auth_limiter=RateLimiter(burst=1, per_minute=1))
    assert bad_login(client, Origin="https://evil.example").status_code == 403
    assert bad_login(client).status_code == 401  # the only token is still there


def test_forwarded_for_uses_the_last_hop_and_only_when_trusted():
    trusted = make_client(Settings(trust_proxy=True), auth_limiter=RateLimiter(burst=1, per_minute=1))
    assert bad_login(trusted, **{"X-Forwarded-For": "9.9.9.9, 1.1.1.1"}).status_code == 401
    # A spoofed first entry does not buy a fresh bucket: same last hop, same bucket
    assert bad_login(trusted, **{"X-Forwarded-For": "8.8.8.8, 1.1.1.1"}).status_code == 429
    assert bad_login(trusted, **{"X-Forwarded-For": "8.8.8.8, 2.2.2.2"}).status_code == 401


def test_forwarded_for_is_ignored_when_not_trusted():
    client = make_client(auth_limiter=RateLimiter(burst=1, per_minute=1))  # trust_proxy=False
    assert bad_login(client, **{"X-Forwarded-For": "1.1.1.1"}).status_code == 401
    # Different header, same socket address: still the same bucket
    assert bad_login(client, **{"X-Forwarded-For": "2.2.2.2"}).status_code == 429