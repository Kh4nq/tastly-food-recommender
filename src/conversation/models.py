"""Internal routing and service envelopes; public preference contracts stay stable."""

from typing import Literal

from pydantic import Field

from common.schemas import PreferenceUpdate, Schema, UserPreferenceState

ConversationIntent = Literal["search", "refinement", "informational", "conversation", "clarification"]


class RuleParseResult(Schema):
    update: PreferenceUpdate
    requires_llm: bool
    matched_spans: list[str] = Field(default_factory=list)
    unresolved_text: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class ParserMetadata(Schema):
    original_message: str | None = None
    parsed_message: str | None = None
    input_normalized: bool = False
    translation_attempted: bool = False
    translation_succeeded: bool = False
    translation_error: str | None = None
    parser_used: Literal["rule", "hybrid_llm", "hybrid_slm", "rule_fallback", "llm", "slm"] = "rule"
    intent: ConversationIntent = "search"
    assistant_message: str | None = None
    slm_enabled: bool = False
    slm_called: bool = False
    slm_backend: str = "disabled"
    slm_confidence: float | None = None
    slm_fallback: bool = False
    slm_error: str | None = None
    slm_ms: float = 0
    llm_called: bool = False
    provider: str | None = None
    requires_llm: bool = False
    partial_result: bool = False
    llm_error: str | None = None
    clarification_required: bool = False
    rule_parse_ms: float = 0
    llm_ms: float = 0
    total_ms: float = 0
    latency_ms: float = 0
    logging_error: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)
    cost_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    provider_attempts: int | None = Field(default=None, ge=0)
    provider_models: list[str] = Field(default_factory=list)
    provider_errors: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    state_preserved: bool = False


class ParseResult(Schema):
    preference_update: PreferenceUpdate
    rule_result: RuleParseResult
    metadata: ParserMetadata


class ConversationResult(ParseResult):
    state: UserPreferenceState
