"""Official Google GenAI adapter; one generate_content request, no retries."""

from common.schemas import PreferenceUpdate, PreviousResult, UserPreferenceState
from pydantic import ValidationError
from conversation.prompts import SYSTEM_PROMPT, build_context
from conversation.providers.base import ProviderError
from conversation.providers.structured import StructuredPreferenceUpdate


class GeminiProvider:
    name = "gemini"

    def __init__(self, *, api_key: str | None, model: str | None) -> None:
        if not api_key or not api_key.strip():
            raise ProviderError("Set GEMINI_API_KEY")
        if not model or not model.strip():
            raise ProviderError("Set GEMINI_MODEL explicitly; no default model is selected")
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ProviderError("Install the gemini extra: pip install -e '.[gemini]'") from None
        try:
            self._client = genai.Client(vertexai=False, api_key=api_key, http_options=types.HttpOptions(
                timeout=30000, retry_options=types.HttpRetryOptions(attempts=1),
            ))
        except Exception:
            raise ProviderError("Gemini client initialization failed; check SDK and environment configuration") from None
        self.model = model
        self.last_usage: dict[str, int] = {}

    def parse_preference(
        self, *, message: str, current_state: UserPreferenceState | None,
        previous_results: list[PreviousResult], rule_update: PreferenceUpdate | None = None,
    ) -> PreferenceUpdate:
        self.last_usage = {}
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=build_context(message=message, current_state=current_state,
                                       previous_results=previous_results, rule_update=rule_update),
                config={"system_instruction": SYSTEM_PROMPT,
                        "response_mime_type": "application/json",
                        "response_json_schema": StructuredPreferenceUpdate.model_json_schema(),
                        "automatic_function_calling": {"disable": True}},
            )
        except TimeoutError:
            raise ProviderError("Gemini request timed out", code="timeout") from None
        except Exception:
            raise ProviderError("Gemini request failed") from None
        # Observability must never invalidate a response, including unknown SDK metadata.
        try:
            usage = getattr(response, "usage_metadata", None)
            for target, source in (("input_tokens", "prompt_token_count"),
                                   ("output_tokens", "candidates_token_count"),
                                   ("total_tokens", "total_token_count")):
                value = getattr(usage, source, None)
                if type(value) is int and value >= 0:
                    self.last_usage[target] = value
        except Exception:
            pass
        try:
            return StructuredPreferenceUpdate.model_validate_json(response.text).to_update()
        except (ValidationError, ValueError, TypeError, AttributeError, RecursionError):
            raise ProviderError("Gemini structured validation failed", code="invalid_output") from None

    def close(self) -> None:
        self._client.close()
