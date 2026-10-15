# Backend settings, read once at startup from environment variables
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from conversation.environment import load_env

ROOT = Path(__file__).resolve().parents[2]  # repository root (editable install)
_ENV_KEYS = ("DATABASE_URL",)
_ENV_PREFIX = "BACKEND_"


def load_environment(path: Path = ROOT / ".env") -> None:
    """Fill os.environ from .env without overriding real environment variables."""
    load_env(path)  # AI 2 keeps its own list of keys (LLM_PROVIDER, GEMINI_*, ...)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        key, sep, value = line.strip().partition("=")
        key = key.strip()
        if sep and (key in _ENV_KEYS or key.startswith(_ENV_PREFIX)):
            os.environ.setdefault(key, value.strip().strip("\"'"))


def _number(env: Mapping[str, str], name: str, cast: Callable, default):
    if name not in env:
        return default
    try:
        value = cast(env[name])
    except ValueError:
        raise ValueError(f"{name} must be a number") from None
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    if name not in env:
        return default
    return env[name].strip().lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class Settings:
    cors_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")
    ai_concurrency: int = 2  # retrieval alone takes ~2s of CPU per call
    ai_queue_timeout_s: float = 5.0  # how long a request may wait for a free AI slot
    ai_timeout_s: float = 30.0  # total limit per request, including the wait for a slot
    cookie_secure: bool = False  # set true when served over HTTPS
    warmup: bool = True  # load data and models at startup instead of on first request
    auth_session_days : int = 7
    auth_max_failures : int = 5
    auth_lock_minutes : int = 15
    auth_hash_concurrency : int = 4
    auth_hash_queue_timeout_s : float = 2.0 # Wait for a hash slot before 503 busy
    # Behind the Next rewrite every visitor shares one IP, so this is a site-wide flood
    # valve, not a per-user limit. Tighten both once a real reverse proxy sets the IP.
    auth_rate_burst : int = 30 # Attempts one IP may make back to back
    auth_rate_per_minute : float = 60.0 # Attempts one IP may make per minute
    trust_proxy : bool = False
    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        defaults = cls()
        origins = defaults.cors_origins
        if "BACKEND_CORS_ORIGINS" in env:
            origins = tuple(o.strip() for o in env["BACKEND_CORS_ORIGINS"].split(",") if o.strip())
        if "*" in origins:
            # Browsers refuse credentials with a wildcard, and cookies are our session
            raise ValueError("BACKEND_CORS_ORIGINS must list explicit origins, not *")
        return cls(
            cors_origins=origins,
            ai_concurrency=_number(env, "BACKEND_AI_CONCURRENCY", int, defaults.ai_concurrency),
            ai_queue_timeout_s=_number(
                env, "BACKEND_AI_QUEUE_TIMEOUT_S", float, defaults.ai_queue_timeout_s
            ),
            ai_timeout_s=_number(env, "BACKEND_AI_TIMEOUT_S", float, defaults.ai_timeout_s),
            cookie_secure=_flag(env, "BACKEND_COOKIE_SECURE", defaults.cookie_secure),
            warmup=_flag(env, "BACKEND_WARMUP", defaults.warmup),
            
            auth_session_days = _number(
                env , "BACKEND_AUTH_SESSION_DAYS", int, defaults.auth_session_days
            ),
            auth_max_failures= _number(
                env, "BACKEND_AUTH_MAX_FAILURES", int, defaults.auth_max_failures
            ),
            auth_lock_minutes= _number(
                env, "BACKEND_AUTH_LOCK_MINUTES", int, defaults.auth_lock_minutes
            ),
            
            auth_hash_concurrency=_number(
                env, "BACKEND_AUTH_HASH_CONCURRENCY", int, defaults.auth_hash_concurrency
            ),
            auth_hash_queue_timeout_s=_number(
                env, "BACKEND_AUTH_HASH_QUEUE_TIMEOUT_S", float, defaults.auth_hash_queue_timeout_s
            ),
            auth_rate_burst=_number(
                env, "BACKEND_AUTH_RATE_BURST", int, defaults.auth_rate_burst
            ),
            auth_rate_per_minute=_number(
                env, "BACKEND_AUTH_RATE_PER_MINUTE", float, defaults.auth_rate_per_minute
            ),
            trust_proxy=_flag(env, "BACKEND_TRUST_PROXY", defaults.trust_proxy),
        )
