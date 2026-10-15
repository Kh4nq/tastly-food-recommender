# Offline HTTP tests for /api/auth, running the app in-process with the in-memory store
import pytest
from fastapi.testclient import TestClient

from backend.adapters.auth_memory import InMemoryAuthStore
from backend.api.deps import Services
from backend.main import create_app
from backend.services import passwords
from backend.services.auth_service import AuthService

PASSWORD = "correct horse"
NEW = dict(role="customer", full_name="An", email="An@X.com", password=PASSWORD)


@pytest.fixture(autouse=True)
def cheap_hashing(monkeypatch):
    monkeypatch.setattr(passwords, "_N", 2**4)  # scrypt is slow on purpose
    monkeypatch.setattr(passwords, "_P", 1)


@pytest.fixture
def client():
    store = InMemoryAuthStore()
    # Search is not involved here, so its parts can be None
    services = Services(search_service=None, presenter=None, auth_service=AuthService(store, store))
    return TestClient(create_app(services))


def register(client, **over):
    return client.post("/api/auth/register", json={**NEW, **over})


def login(client, email="an@x.com", password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def error(response):
    return response.json()["error"]


def test_register_signs_in_and_exposes_only_public_fields(client):
    response = register(client)
    assert response.status_code == 201
    user = response.json()["user"]
    assert set(user) == {"id", "email", "full_name", "phone", "role", "shop_name"}
    assert user["email"] == "an@x.com"

    cookie = response.headers["set-cookie"].lower()
    assert "auth=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert "max-age=604800" in cookie  # cookie lifetime matches the default seven-day session
    assert client.get("/api/auth/me").json()["user"]["email"] == "an@x.com"


@pytest.mark.parametrize("origin", ["http://localhost:3000", "http://127.0.0.1:3000"])
def test_local_frontend_origins_can_sign_in(client, origin):
    register(client)
    response = client.post("/api/auth/login", json={"email": NEW["email"], "password": PASSWORD}, headers={"Origin": origin})
    assert response.status_code == 200


def test_duplicate_email_is_409_in_any_case(client):
    register(client, email="a@x.com")
    response = register(client, email="A@X.COM")
    assert response.status_code == 409 and error(response)["code"] == "email_taken"


@pytest.mark.parametrize("bad", [
    {"password": "short"},
    {"role": "admin"},
    {"role": "business"},  # no shop_name
    {"email": "not-an-email"},
    {"full_name": "   "},
    {"is_admin": True},  # unknown field
])
def test_invalid_registration_is_422(client, bad):
    response = register(client, **bad)
    assert response.status_code == 422 and error(response)["code"] == "validation_error"


def test_validation_error_never_echoes_the_password(client):
    response = register(client, password="p4ssw0r")  # 7 chars, too short
    assert response.status_code == 422
    assert "p4ssw0r" not in response.text


def test_login_succeeds_and_fails_without_telling_why(client):
    register(client)
    client.post("/api/auth/logout")

    assert login(client).status_code == 200

    wrong = login(client, password="wrong password")
    unknown = login(client, email="nobody@x.com")
    assert wrong.status_code == unknown.status_code == 401
    assert error(wrong)["code"] == error(unknown)["code"] == "invalid_credentials"
    assert error(wrong)["message"] == error(unknown)["message"]


def test_account_locks_with_retry_after(client):
    register(client)
    for _ in range(5):
        assert login(client, password="wrong password").status_code == 401

    response = login(client)  # right password, still refused
    assert response.status_code == 429 and error(response)["code"] == "rate_limited"
    assert int(response.headers["retry-after"]) > 0


def test_me_without_a_session_is_401_and_clears_the_cookie(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401 and error(response)["code"] == "unauthenticated"
    assert "max-age=0" in response.headers["set-cookie"].lower()


def test_a_forged_cookie_is_rejected(client):
    client.cookies.set("auth", "1")  # what the old fake login used to set
    assert client.get("/api/auth/me").status_code == 401


def test_logout_revokes_the_session_on_the_server(client):
    register(client)
    token = client.cookies.get("auth")

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401

    client.cookies.set("auth", token)  # replaying the old cookie must not work
    assert client.get("/api/auth/me").status_code == 401


def test_logout_without_a_session_is_still_204(client):
    assert client.post("/api/auth/logout").status_code == 204


def test_change_password_switches_the_password_and_keeps_you_signed_in(client):
    register(client)
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "brand new pass"},
    )
    assert response.status_code == 204
    assert client.get("/api/auth/me").status_code == 200  # got a fresh cookie

    client.post("/api/auth/logout")
    assert login(client, password=PASSWORD).status_code == 401
    assert login(client, password="brand new pass").status_code == 200


def test_change_password_with_wrong_current_is_403(client):
    register(client)
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "not mine", "new_password": "brand new pass"},
    )
    assert response.status_code == 403 and error(response)["code"] == "wrong_password"


def test_update_profile(client):
    register(client)
    response = client.put("/api/auth/me", json={"full_name": " Bình ", "phone": "0901 234 567"})
    assert response.status_code == 200
    assert response.json()["user"]["full_name"] == "Bình"
    assert client.get("/api/auth/me").json()["user"]["phone"] == "0901 234 567"
    
def test_business_cannot_clear_its_shop_name(client):
    register(client, role="business", shop_name="Phở Thìn")
    response = client.put("/api/auth/me", json={"full_name": "An", "phone": None, "shop_name": "  "})
    assert response.status_code == 422 and error(response)["code"] == "validation_error"
