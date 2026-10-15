"""Optional JSONL audit trail with credential redaction and bounded error codes."""

from datetime import datetime, timezone
import json
from pathlib import Path
import re

from pydantic import JsonValue

from common.schemas import UserRequest
from conversation.config import ConversationConfig
from conversation.models import ConversationResult


def _redact(value: JsonValue, secrets: tuple[str | None, ...]) -> JsonValue:
    if isinstance(value, dict):
        return {_redact(key, secrets): (item if key in {"input_tokens", "output_tokens", "total_tokens"} and type(item) is int
                      else "[REDACTED]" if re.search(r"api.?key|authorization|secret|token", key, re.I)
                      else _redact(item, secrets)) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"(?i)bearer\s+\S+|\bsk-[\w-]+|\bAIza[\w-]+", "[REDACTED]", value)
        value = re.sub(r"(?i)((?:api[_ -]?key|secret|authorization)\s*[:=]\s*)\S+",
                       r"\1[REDACTED]", value)
    return value


def log_conversation(request: UserRequest, result: ConversationResult,
                     config: ConversationConfig) -> str | None:
    """Logging failure never invalidates an otherwise successful state update."""
    if not config.log_enabled:
        return None
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": request.session_id, "user_id": request.user_id or result.state.user_id,
        "message": request.message,
        **result.metadata.model_dump(mode="json", exclude={"assistant_message"}),
        "preference_update": result.preference_update.model_dump(mode="json"),
        "error": result.metadata.llm_error,
    }
    try:
        path = Path(config.log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _redact(record, (config.openai_api_key, config.gemini_api_key, config.openrouter_api_key))
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n")
    except (OSError, ValueError):
        return "log_write_failed"
    return None
