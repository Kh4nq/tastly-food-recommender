"""Explicit repository environment loading for command-line tools."""

import os
from pathlib import Path


def load_env(path: Path = Path(__file__).resolve().parents[2] / ".env") -> None:
    """Load simple KEY=value entries without interpolation or overriding environment."""
    allowed = {"LLM_PROVIDER", "GEMINI_API_KEY", "GEMINI_MODEL", "OPENAI_API_KEY",
               "OPENAI_MODEL", "CONVERSATION_LOG_ENABLED", "CONVERSATION_LOG_PATH",
               "LOCAL_SLM_ENABLED", "LOCAL_SLM_BACKEND", "LOCAL_SLM_BASE_MODEL",
               "LOCAL_SLM_ADAPTER_VERSION", "LOCAL_SLM_ADAPTER_PATH", "LOCAL_SLM_MODEL",
               "LOCAL_SLM_LOCAL_FILES_ONLY", "LOCAL_SLM_MAX_NEW_TOKENS", "LOCAL_SLM_MIN_CONFIDENCE",
               "AI2_INPUT_NORMALIZATION_ENABLED", "AI2_TRANSLATION_ENABLED",
               "OPENROUTER_ENABLED", "OPENROUTER_API_KEY", "OPENROUTER_MODEL",
               "OPENROUTER_TIMEOUT", "OPENROUTER_MAX_RETRIES", "OPENROUTER_MAX_TOKENS",
               "OPENROUTER_STRUCTURED_OUTPUT", "OPENROUTER_PRIMARY_MODEL", "OPENROUTER_BACKUP_MODEL",
               "OPENROUTER_CHAIN_MAX_TOKENS", "AI2_LLM_FIRST_ENABLED", "AI2_RULE_FALLBACK_ENABLED",
               "LOCAL_SLM_FALLBACK_ADAPTER_PATH"}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.strip().removeprefix("export ").partition("=")
            if sep and key.strip() in allowed:
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                os.environ.setdefault(key.strip(), value)
