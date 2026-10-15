"""Environment configuration read per request; no SDK imports or global state."""

from dataclasses import dataclass, field
import os
import math

from conversation.providers.base import LLMProvider, ProviderError
from conversation.providers.openai_provider import DEFAULT_OPENAI_MODEL


@dataclass(frozen=True)
class ConversationConfig:
    llm_provider: str = "none"
    openai_api_key: str | None = field(default=None, repr=False)
    openai_model: str | None = DEFAULT_OPENAI_MODEL
    gemini_api_key: str | None = field(default=None, repr=False)
    gemini_model: str | None = None
    log_enabled: bool = False
    log_path: str = "logs/conversation.jsonl"
    local_slm_enabled: bool = False
    local_slm_backend: str = "qwen_lora"
    local_slm_model: str = ""
    local_slm_min_confidence: float = 0.80
    local_slm_base_model: str = "Qwen/Qwen3-1.7B"
    local_slm_adapter_path: str = "models/ai2/ai2-qwen3-1.7b-lora-targeted-v3"
    local_slm_max_new_tokens: int = 512
    input_normalization_enabled: bool = True
    translation_enabled: bool = False
    local_slm_local_files_only: bool = True
    openrouter_enabled: bool = False
    openrouter_api_key: str | None = field(default=None, repr=False)
    openrouter_model: str = "qwen/qwen3-32b"
    openrouter_timeout: float = 30.0
    openrouter_max_retries: int = 0
    openrouter_structured_output: bool = False
    openrouter_max_tokens: int = 1024
    openrouter_primary_model: str = "google/gemini-3.5-flash-lite"
    openrouter_backup_model: str = "openai/gpt-5.4-mini"
    openrouter_chain_max_tokens: int = 512
    llm_first_enabled: bool = True
    rule_fallback_enabled: bool = False
    local_slm_fallback_adapter_path: str = "models/ai2/best_adapter_v4_experimental"

    def __post_init__(self):
        if not 0 <= self.local_slm_min_confidence <= 1:
            raise ValueError("LOCAL_SLM_MIN_CONFIDENCE must be between 0 and 1")
        if type(self.local_slm_max_new_tokens) is not int or not 1 <= self.local_slm_max_new_tokens <= 4096:
            raise ValueError("LOCAL_SLM_MAX_NEW_TOKENS must be an integer between 1 and 4096")
        if not math.isfinite(self.openrouter_timeout) or self.openrouter_timeout <= 0:
            raise ValueError("OPENROUTER_TIMEOUT must be finite and positive")
        if type(self.openrouter_max_retries) is not int or not 0 <= self.openrouter_max_retries <= 2:
            raise ValueError("OPENROUTER_MAX_RETRIES must be between 0 and 2")
        if type(self.openrouter_max_tokens) is not int or not 1 <= self.openrouter_max_tokens <= 4096:
            raise ValueError("OPENROUTER_MAX_TOKENS must be between 1 and 4096")
        if type(self.openrouter_chain_max_tokens) is not int or not 1 <= self.openrouter_chain_max_tokens <= 4096:
            raise ValueError("OPENROUTER_CHAIN_MAX_TOKENS must be between 1 and 4096")
        if self.llm_provider == "openrouter_chain" and (
            self.openrouter_primary_model != "google/gemini-3.5-flash-lite" or
            self.openrouter_backup_model != "openai/gpt-5.4-mini"
        ):
            raise ValueError("OpenRouter chain requires the agreed primary/backup profiles")

    @classmethod
    def from_env(cls) -> "ConversationConfig":
        version = os.getenv("LOCAL_SLM_ADAPTER_VERSION", "v3").strip().lower()
        adapters = {"v3": "models/ai2/ai2-qwen3-1.7b-lora-targeted-v3",
                    "v4": "models/ai2/best_adapter_v4_experimental"}
        if version not in adapters:
            raise ValueError("LOCAL_SLM_ADAPTER_VERSION must be v3 or v4")
        return cls(
            llm_provider=os.getenv("LLM_PROVIDER", "none").strip().lower(),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model=os.getenv("OPENAI_MODEL", "").strip() or DEFAULT_OPENAI_MODEL,
            gemini_api_key=os.getenv("GEMINI_API_KEY"), gemini_model=os.getenv("GEMINI_MODEL"),
            log_enabled=os.getenv("CONVERSATION_LOG_ENABLED", "false").lower() in ("true", "1", "yes"),
            log_path=os.getenv("CONVERSATION_LOG_PATH", "logs/conversation.jsonl"),
            local_slm_enabled=os.getenv("LOCAL_SLM_ENABLED", "false").lower() in ("true", "1", "yes"),
            local_slm_backend=os.getenv("LOCAL_SLM_BACKEND", "qwen_lora").strip().lower(),
            local_slm_model=os.getenv("LOCAL_SLM_MODEL", ""),
            local_slm_min_confidence=float(os.getenv("LOCAL_SLM_MIN_CONFIDENCE", "0.80")),
            local_slm_base_model=os.getenv("LOCAL_SLM_BASE_MODEL", "Qwen/Qwen3-1.7B"),
            local_slm_adapter_path=os.getenv("LOCAL_SLM_ADAPTER_PATH", "").strip() or adapters[version],
            local_slm_max_new_tokens=int(os.getenv("LOCAL_SLM_MAX_NEW_TOKENS", "512")),
            input_normalization_enabled=os.getenv("AI2_INPUT_NORMALIZATION_ENABLED", "true").lower() in ("true", "1", "yes"),
            translation_enabled=os.getenv("AI2_TRANSLATION_ENABLED", "false").lower() in ("true", "1", "yes"),
            local_slm_local_files_only=os.getenv("LOCAL_SLM_LOCAL_FILES_ONLY", "true").lower() in ("true", "1", "yes"),
            openrouter_enabled=os.getenv("OPENROUTER_ENABLED", "false").lower() in ("true", "1", "yes"),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
            openrouter_model=os.getenv("OPENROUTER_MODEL", "").strip() or "qwen/qwen3-32b",
            openrouter_timeout=float(os.getenv("OPENROUTER_TIMEOUT", "30")),
            openrouter_max_retries=int(os.getenv("OPENROUTER_MAX_RETRIES", "0")),
            openrouter_structured_output=os.getenv("OPENROUTER_STRUCTURED_OUTPUT", "false").lower() in ("true", "1", "yes"),
            openrouter_max_tokens=int(os.getenv("OPENROUTER_MAX_TOKENS", "1024")),
            openrouter_primary_model=os.getenv("OPENROUTER_PRIMARY_MODEL", "google/gemini-3.5-flash-lite"),
            openrouter_backup_model=os.getenv("OPENROUTER_BACKUP_MODEL", "openai/gpt-5.4-mini"),
            openrouter_chain_max_tokens=int(os.getenv("OPENROUTER_CHAIN_MAX_TOKENS", "512")),
            llm_first_enabled=os.getenv("AI2_LLM_FIRST_ENABLED", "true").lower() in ("true", "1", "yes"),
            rule_fallback_enabled=os.getenv("AI2_RULE_FALLBACK_ENABLED", "false").lower() in ("true", "1", "yes"),
            local_slm_fallback_adapter_path=os.getenv("LOCAL_SLM_FALLBACK_ADAPTER_PATH", "models/ai2/best_adapter_v4_experimental"),
        )


def create_provider(config: ConversationConfig) -> LLMProvider:
    if config.llm_provider == "openrouter_chain":
        return create_chain_provider(config, backup=False)
    if config.llm_provider == "openrouter":
        from conversation.providers.openrouter_provider import OpenRouterProvider
        return OpenRouterProvider(api_key=config.openrouter_api_key, model=config.openrouter_model,
            enabled=config.openrouter_enabled, timeout=config.openrouter_timeout,
            max_retries=config.openrouter_max_retries, structured_output=config.openrouter_structured_output,
            max_tokens=config.openrouter_max_tokens)
    if config.llm_provider == "mock":
        from conversation.providers.mock import MockProvider
        return MockProvider()
    if config.llm_provider == "openai":
        from conversation.providers.openai_provider import OpenAIProvider
        return OpenAIProvider(api_key=config.openai_api_key, model=config.openai_model)
    if config.llm_provider == "gemini":
        from conversation.providers.gemini_provider import GeminiProvider
        return GeminiProvider(api_key=config.gemini_api_key, model=config.gemini_model)
    raise ProviderError("LLM provider is not configured or unsupported")


def create_chain_provider(config: ConversationConfig, *, backup: bool) -> LLMProvider:
    from conversation.providers.openrouter_provider import OpenRouterProvider
    return OpenRouterProvider(api_key=config.openrouter_api_key,
        model=config.openrouter_backup_model if backup else config.openrouter_primary_model,
        enabled=config.openrouter_enabled, timeout=config.openrouter_timeout, max_retries=0,
        structured_output=True, max_tokens=config.openrouter_chain_max_tokens, verified_profile=True)
