import pytest

from backend.settings import Settings, load_environment


def test_defaults_need_no_environment():
    settings = Settings.from_env({})
    assert settings.cors_origins == ("http://localhost:3000", "http://127.0.0.1:3000")
    assert settings.ai_concurrency == 2
    assert settings.cookie_secure is False and settings.warmup is True
    assert settings.auth_session_days == 7
    assert settings.auth_max_failures == 5 and settings.auth_lock_minutes == 15
    assert settings.auth_hash_concurrency == 4 and settings.auth_hash_queue_timeout_s == 2.0
    assert settings.auth_rate_burst == 30 and settings.auth_rate_per_minute == 60.0
    assert settings.trust_proxy is False

def test_values_are_read_and_parsed():
    settings = Settings.from_env(
        {
            "BACKEND_CORS_ORIGINS": "https://a.example, https://b.example ,",
            "BACKEND_AI_CONCURRENCY": "4",
            "BACKEND_AI_QUEUE_TIMEOUT_S": "0.5",
            "BACKEND_AI_TIMEOUT_S": "12",
            "BACKEND_COOKIE_SECURE": "true",
            "BACKEND_WARMUP": "0",
            "BACKEND_AUTH_HASH_CONCURRENCY": "1",
            "BACKEND_AUTH_HASH_QUEUE_TIMEOUT_S": "0.5",
            "BACKEND_AUTH_RATE_BURST": "3",
            "BACKEND_AUTH_RATE_PER_MINUTE": "2.5",
            "BACKEND_TRUST_PROXY": "yes",
        }
    )
    assert settings.cors_origins == ("https://a.example", "https://b.example")
    assert settings.ai_concurrency == 4 and settings.ai_queue_timeout_s == 0.5
    assert settings.ai_timeout_s == 12.0
    assert settings.cookie_secure is True and settings.warmup is False
    assert settings.auth_hash_concurrency == 1 and settings.auth_hash_queue_timeout_s == 0.5
    assert settings.auth_rate_burst == 3 and settings.auth_rate_per_minute == 2.5
    assert settings.trust_proxy is True

@pytest.mark.parametrize(
    "env",
    [
        {"BACKEND_AI_CONCURRENCY": "0"},
        {"BACKEND_AI_TIMEOUT_S": "-1"},
        {"BACKEND_AI_CONCURRENCY": "many"},
        {"BACKEND_CORS_ORIGINS": "*"},
        {"BACKEND_AUTH_MAX_FAILURES": "0"},
        {"BACKEND_AUTH_LOCK_MINUTES": "soon"},
        {"BACKEND_AUTH_HASH_CONCURRENCY": "0"},
        {"BACKEND_AUTH_RATE_BURST": "-5"},
        {"BACKEND_AUTH_RATE_PER_MINUTE": "fast"},
    ],
)
def test_bad_values_fail_at_startup(env):
    with pytest.raises(ValueError):
        Settings.from_env(env)


def test_dotenv_fills_only_known_keys_and_never_overrides(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://u:p@127.0.0.1/db\n"
        "BACKEND_WARMUP=false\n"
        "BACKEND_AI_CONCURRENCY=9\n"
        "UNRELATED_SECRET=nope\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("BACKEND_WARMUP", raising=False)
    monkeypatch.delenv("UNRELATED_SECRET", raising=False)
    monkeypatch.setenv("BACKEND_AI_CONCURRENCY", "3")  # a real variable wins over .env
    load_environment(env_file)
    import os

    assert os.environ["DATABASE_URL"].startswith("postgresql://")
    assert os.environ["BACKEND_WARMUP"] == "false"
    assert os.environ["BACKEND_AI_CONCURRENCY"] == "3"
    assert "UNRELATED_SECRET" not in os.environ
    # monkeypatch cannot undo keys that load_environment added itself
    for key in ("DATABASE_URL", "BACKEND_WARMUP"):
        os.environ.pop(key, None)
