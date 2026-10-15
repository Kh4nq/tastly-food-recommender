"""Official OpenAI Responses adapter; one request with SDK retries disabled."""

from common.schemas import PreferenceUpdate, PreviousResult, UserPreferenceState
from pydantic import ValidationError
from conversation.prompts import SYSTEM_PROMPT, build_context
from conversation.providers.base import ProviderError
from conversation.providers.structured import StructuredPreferenceUpdate

DEFAULT_OPENAI_MODEL = "gpt-5.6-luna"


class OpenAIProvider:
    name = "openai"

    def __init__(self, *, api_key: str | None, model: str | None = None) -> None:
        if not api_key or not api_key.strip():
            raise ProviderError("Set OPENAI_API_KEY")
        try:
            from openai import OpenAI
        except ImportError:
            raise ProviderError("Install the openai extra: pip install -e '.[openai]'") from None
        try:
            self._client = OpenAI(api_key=api_key, max_retries=0, timeout=30.0)
        except Exception:
            raise ProviderError("OpenAI client initialization failed; check SDK and environment configuration") from None
        self.model = (model or "").strip() or DEFAULT_OPENAI_MODEL
        self.last_usage: dict[str, int] = {}

    def parse_preference(
        self, *, message: str, current_state: UserPreferenceState | None,
        previous_results: list[PreviousResult], rule_update: PreferenceUpdate | None = None,
    ) -> PreferenceUpdate:
        self.last_usage = {}
        try:
            response = self._client.responses.parse(
                model=self.model, instructions=SYSTEM_PROMPT,
                input=build_context(message=message, current_state=current_state,
                                    previous_results=previous_results, rule_update=rule_update),
                text_format=StructuredPreferenceUpdate,
            )
        except Exception as exc:
            # Never copy SDK exception text, headers, response bodies or credentials.
            status = getattr(exc, "status_code", None)
            if isinstance(exc, TimeoutError) or type(exc).__name__ == "APITimeoutError":
                code = "timeout"
            elif status == 429:
                code = "rate_limit"
            elif status in (401, 403):
                code = "authentication_error"
            elif isinstance(exc, ValidationError):
                code = "invalid_output"
            else:
                code = "provider_error"
            raise ProviderError("OpenAI request failed", code=code) from None
        try:
            usage = getattr(response, "usage", None)
            for key in ("input_tokens", "output_tokens", "total_tokens"):
                value = getattr(usage, key, None)
                if type(value) is int and value >= 0:
                    self.last_usage[key] = value
        except Exception:
            pass
        try:
            return StructuredPreferenceUpdate.model_validate(response.output_parsed).to_update()
        except (ValidationError, ValueError, TypeError, AttributeError):
            raise ProviderError("OpenAI structured validation failed", code="invalid_output") from None

    def close(self) -> None:
        self._client.close()
