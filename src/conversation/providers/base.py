"""Provider boundary. Legacy adapters use one call; OpenRouter retries are opt-in."""

from typing import Protocol

from common.schemas import PreferenceUpdate, PreviousResult, UserPreferenceState


class ProviderError(RuntimeError):
    """Controlled provider failure; messages must never contain secrets."""

    def __init__(self, message: str, *, code: str = "provider_error") -> None:
        super().__init__(message)
        self.code = code if code in {"provider_error", "invalid_output", "timeout",
                                    "rate_limit", "authentication_error"} else "provider_error"


class LLMProvider(Protocol):
    name: str

    def parse_preference(
        self, *, message: str, current_state: UserPreferenceState | None,
        previous_results: list[PreviousResult], rule_update: PreferenceUpdate | None = None,
    ) -> PreferenceUpdate: ...
