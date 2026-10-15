"""Artifact envelopes reuse the authoritative public preference contracts."""
from datetime import datetime, timezone
from typing import Literal

from pydantic import Field

from common.schemas import Candidate, PreferenceUpdate, PreviousResult, Schema, UserPreferenceState
from conversation.models import ParserMetadata, RuleParseResult


class PromptSample(Schema):
    sample_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    message: str = Field(min_length=1)
    current_state: UserPreferenceState | None = None
    previous_results: list[PreviousResult] = Field(default_factory=list)
    source: str = "synthetic_template"
    generation: dict = Field(default_factory=dict)
    history: list[str] = Field(default_factory=list)
    mock_candidates: list[Candidate] = Field(default_factory=list)


class TeacherLabel(Schema):
    sample_id: str
    sample_hash: str
    rule_result: RuleParseResult
    rule_candidate: PreferenceUpdate
    rule_resolved: bool
    routing: ParserMetadata
    provider: Literal["rule", "gemini"]
    model: str | None = None
    teacher_prediction: dict | None = None
    candidate: dict | None = None
    status: Literal["completed", "error", "attempt_reserved"] = "completed"
    error: str | None = None
    retryable: bool = False
    attempts: int = Field(default=0, ge=0, le=1)
    latency_ms: float = Field(default=0, ge=0)


class ValidationResult(Schema):
    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)


class ReviewItem(Schema):
    sample: PromptSample
    teacher: TeacherLabel
    validation: ValidationResult
    disagreement: bool
    priority: Literal["high", "medium", "low"]


class ReviewRecord(Schema):
    sample_id: str
    item_hash: str
    original_teacher_prediction: dict | None
    original_candidate: dict | None
    final_label: dict | None
    action: Literal["accepted", "corrected", "rejected", "skipped"]
    note: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TrainingRecord(Schema):
    schema_version: Literal["0.2"] = "0.2"
    input: dict
    target: PreferenceUpdate
    metadata: dict
