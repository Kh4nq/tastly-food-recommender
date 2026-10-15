> Historical development report. Use the [public README](../README.md) and [setup guide](setup.md) for the current distribution.

# External fallback audit and OpenRouter preparation

Gemini remains selected by the existing team configuration (`LLM_PROVIDER=gemini`).
Core ConversationConfig continues to default to `none`; it does not load .env.
Gemini requires an explicit model ID and environment key; no new model was chosen.
Its official google-genai client has a 30,000 ms timeout and attempts=1 (no retries).
Output passes StructuredPreferenceUpdate then public PreferenceUpdate conversion,
parser evidence validation and a trial State Manager application. Usage token
counts are captured. TimeoutError is classified as timeout; other SDK exceptions
remain sanitized generic provider_error. The existing adapter has no cost data.
No live Gemini call or replacement of Gemini's policy occurred.

OpenRouter implements the same parse_preference boundary, selected only when both
`LLM_PROVIDER=openrouter` and `OPENROUTER_ENABLED=true`. Keys are private config
fields, never frontend configuration. Defaults: qwen/qwen3-32b, 30-second request
budget, zero retries, max_tokens=1024. Set model to `deepseek/deepseek-v3.2` for
the alternative. HTTP transport uses Python's standard library, avoiding an SDK
dependency and import-time network/client creation.

JSON-object mode requests the existing closed wire projection; optional schema
mode sends its JSON schema with strict=true. Both use require_parameters=true:
an incompatible endpoint fails instead of silently dropping the requested format.
The API documents endpoint-specific support, so enable schema mode only after
checking that endpoint's supported parameters. No compatibility claim is based
solely on the model name. See [structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs)
and [API reference](https://openrouter.ai/docs/api_reference/overview).

Duplicate keys, non-finite numbers, invalid schemas, refusals and truncated outputs
are rejected. HTTP auth/rate-limit/timeout errors become bounded safe codes; raw
provider bodies, headers, exception strings and keys are not logged. Retries can
be configured from 0 to 2 only for 429/502/503/504, with bounded backoff within
the request budget. Timeout/ambiguous connection failures and invalid JSON are
not retried automatically; an earlier attempt may already be billed.

Token usage and the API's returned usage.cost are retained even when the model
output fails validation. Missing cost remains unknown (null), never estimated
from fixed prices; retry failures lacking usage cannot establish a full bill.
See [usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting).
Conversation metadata/logs expose safe token counts, cost and attempt counts.
Normal backend public responses expose only existing turn fields.

Mock tests need no real key/credits. No paid endpoint, balance endpoint or payment
flow was called. Later activation requires the server environment settings in
`AI2_RUNTIME_ENV.example`; enabling the flag alone does not replace Gemini.
