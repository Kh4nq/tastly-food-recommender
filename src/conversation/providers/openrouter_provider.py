"""Opt-in OpenRouter Chat Completions boundary; no client/import-time I/O."""
import json
import math
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from conversation.prompts import SYSTEM_PROMPT, CONVERSATION_PROMPT, build_context
from conversation.providers.base import ProviderError
from conversation.providers.structured import StructuredPreferenceUpdate, StructuredConversationTurn
from conversation.slm.qwen_lora import _unique_object, _invalid_constant

DEFAULT_OPENROUTER_MODEL = "qwen/qwen3-32b"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterProvider:
    name = "openrouter"

    def __init__(self, *, api_key, model=DEFAULT_OPENROUTER_MODEL, enabled=False,
                 timeout=30.0, max_retries=0, structured_output=False, max_tokens=1024,
                 verified_profile=False):
        if not enabled:
            raise ProviderError("OpenRouter is disabled; set OPENROUTER_ENABLED explicitly")
        if not api_key or not api_key.strip():
            raise ProviderError("Set OPENROUTER_API_KEY", code="authentication_error")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("OpenRouter timeout must be finite and positive")
        if type(max_retries) is not int or not 0 <= max_retries <= 2:
            raise ValueError("OpenRouter retries must be between 0 and 2")
        if type(max_tokens) is not int or not 1 <= max_tokens <= 4096:
            raise ValueError("OpenRouter max_tokens must be between 1 and 4096")
        self._api_key = api_key
        self.model = model.strip() or DEFAULT_OPENROUTER_MODEL
        self.timeout, self.max_retries = timeout, max_retries
        self.structured_output, self.max_tokens = structured_output, max_tokens
        self.verified_profile = verified_profile
        if verified_profile and self.model not in {"google/gemini-3.5-flash-lite", "openai/gpt-5.4-mini"}:
            raise ValueError("Unsupported production OpenRouter profile")
        self.last_usage = {}
        self.last_cost_usd = None
        self.last_attempts = 0

    def parse_preference(self, **kwargs):
        return self._interpret(StructuredPreferenceUpdate, SYSTEM_PROMPT, **kwargs).to_update()

    def interpret_turn(self, **kwargs):
        return self._interpret(StructuredConversationTurn, CONVERSATION_PROMPT, **kwargs)

    def _interpret(self, output_type, system_prompt, *, message, current_state, previous_results, rule_update=None):
        context = build_context(message=message, current_state=current_state,
                                previous_results=previous_results, rule_update=rule_update)
        schema_name = 'conversation_turn' if output_type is StructuredConversationTurn else 'preference_update'
        self.last_usage, self.last_cost_usd, self.last_attempts = {}, None, 0
        response_format = {"type": "json_object"}
        if self.structured_output:
            response_format = {"type": "json_schema", "json_schema": {
                "name": schema_name, "strict": True,
                "schema": output_type.model_json_schema()}}
        payload = {
            "model": self.model, "temperature": 0, "stream": False,
            "max_tokens": self.max_tokens, "response_format": response_format,
            "provider": {"require_parameters": True},
            "messages": [{"role": "system", "content": system_prompt +
                          ("\nReturn JSON matching this schema:\n" + json.dumps(output_type.model_json_schema())
                           if not self.structured_output else "")},
                         {"role": "user", "content": context}],
        }
        if self.verified_profile:
            payload["provider"]["allow_fallbacks"] = False
            if self.model == "google/gemini-3.5-flash-lite":
                payload["reasoning"] = {"enabled": True}
            else:
                payload.pop("temperature")
                payload["reasoning"] = {"effort": "none"}
        deadline = time.monotonic() + self.timeout
        request = Request(ENDPOINT, data=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode(),
                          headers={"Authorization": "Bearer " + self._api_key,
                                   "Content-Type": "application/json"}, method="POST")
        for attempt in range(self.max_retries + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProviderError("OpenRouter request timed out", code="timeout")
            self.last_attempts += 1
            try:
                with urlopen(request, timeout=remaining) as response:
                    # Bound response memory; responses are never printed or logged here.
                    body = response.read(2_000_001)
                if len(body) > 2_000_000:
                    raise ProviderError("OpenRouter response too large", code="invalid_output")
                break
            except HTTPError as exc:
                status = exc.code
                exc.close()
                if status in (429, 502, 503, 504) and attempt < self.max_retries:
                    delay = min(2 ** attempt, max(0, deadline - time.monotonic()))
                    time.sleep(delay)
                    continue
                code = "rate_limit" if status == 429 else "authentication_error" if status in (401, 403) else "provider_error"
                raise ProviderError("OpenRouter request failed", code=code) from None
            except (TimeoutError, URLError) as exc:
                code = "timeout" if isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError) else "provider_error"
                # A timeout may already be billed; do not blindly retry it.
                raise ProviderError("OpenRouter request failed", code=code) from None
            except ProviderError:
                raise
            except Exception:
                raise ProviderError("OpenRouter request failed") from None
        try:
            response = json.loads(body, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
            usage = response.get("usage", {})
            if isinstance(usage, dict):
                for target, source in (("input_tokens", "prompt_tokens"),
                                       ("output_tokens", "completion_tokens"), ("total_tokens", "total_tokens")):
                    value = usage.get(source)
                    if type(value) is int and value >= 0:
                        self.last_usage[target] = value
                cost = usage.get("cost")
                if type(cost) in (int, float) and math.isfinite(cost) and cost >= 0:
                    self.last_cost_usd = float(cost)
            if self.verified_profile and response.get("model") != self.model:
                raise ValueError("Unexpected returned model identity")
            choice = response["choices"][0]
            if choice.get("finish_reason") != "stop" or choice["message"].get("refusal"):
                raise ValueError("Incomplete/refused output")
            content = json.loads(choice["message"]["content"], object_pairs_hook=_unique_object,
                                 parse_constant=_invalid_constant)
            return output_type.model_validate(content)
        except (ValidationError, ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError):
            raise ProviderError("OpenRouter structured validation failed", code="invalid_output") from None

    def close(self):
        """No persistent client resources."""
