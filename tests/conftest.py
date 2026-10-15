"""Tests are offline even when the developer has real provider env configured."""

import socket

import pytest


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    for key in ("LLM_PROVIDER", "OPENAI_API_KEY", "OPENAI_MODEL", "GEMINI_API_KEY",
                "GEMINI_MODEL", "CONVERSATION_LOG_ENABLED", "CONVERSATION_LOG_PATH",
                "LOCAL_SLM_ENABLED", "LOCAL_SLM_BACKEND", "LOCAL_SLM_MODEL", "LOCAL_SLM_MIN_CONFIDENCE",
                "LOCAL_SLM_BASE_MODEL", "LOCAL_SLM_ADAPTER_PATH", "LOCAL_SLM_MAX_NEW_TOKENS",
                "AI2_INPUT_NORMALIZATION_ENABLED", "AI2_TRANSLATION_ENABLED",
                "LOCAL_SLM_ADAPTER_VERSION", "LOCAL_SLM_LOCAL_FILES_ONLY",
                "OPENROUTER_ENABLED", "OPENROUTER_API_KEY", "OPENROUTER_MODEL",
                "OPENROUTER_TIMEOUT", "OPENROUTER_MAX_RETRIES", "OPENROUTER_MAX_TOKENS",
                "OPENROUTER_STRUCTURED_OUTPUT", "OPENROUTER_PRIMARY_MODEL", "OPENROUTER_BACKUP_MODEL",
                "OPENROUTER_CHAIN_MAX_TOKENS", "AI2_LLM_FIRST_ENABLED", "AI2_RULE_FALLBACK_ENABLED",
                "LOCAL_SLM_FALLBACK_ADAPTER_PATH"):
        monkeypatch.delenv(key, raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("Network is forbidden in unit tests")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
