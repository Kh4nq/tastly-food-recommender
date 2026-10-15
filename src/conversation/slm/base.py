"""Frozen inference boundary: no runtime, weights or training dependencies."""
from typing import Protocol
from pydantic import Field
from common.schemas import PreferenceUpdate, PreviousResult, Schema, UserPreferenceState, JsonValue
from conversation.models import RuleParseResult


class SLMInput(Schema):
    message: str
    current_state: UserPreferenceState | None = None
    rule_result: RuleParseResult
    previous_results: list[PreviousResult] = Field(default_factory=list)


class SLMParseResult(Schema):
    update: PreferenceUpdate
    confidence: float = Field(ge=0, le=1, strict=True)
    should_fallback: bool = Field(default=False, strict=True)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class SLMProvider(Protocol):
    def parse(self, request: SLMInput) -> SLMParseResult: ...
