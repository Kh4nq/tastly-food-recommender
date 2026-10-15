"""Closed wire projection of PreferenceUpdate for strict provider JSON schemas.

The public contract allows arbitrary JSON dictionaries. Strict structured output
requires declared object fields; key/value entries keep constraints extensible.
"""

from typing import Literal

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr, field_validator, model_validator

from common.schemas import Direction, Location, PreferenceUpdate, Schema, UserPreferenceState, validate_known_constraint
from conversation.models import ConversationIntent

ConstraintValue = StrictStr | StrictInt | StrictFloat | StrictBool | list[StrictStr]
RESERVED_CONSTRAINT_KEYS = frozenset(UserPreferenceState.model_fields)


class SetValues(Schema):
    food: list[str] | None
    cuisine: list[str] | None
    location: Location | None


class ConstraintEntry(Schema):
    """An extensible constraint; values are scalars or string lists, never objects."""

    key: str = Field(description="Short consistent snake_case key; not a state/system field")
    value: ConstraintValue

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        key = value.strip().lower()
        if not key:
            raise ValueError("Constraint key must not be empty")
        if key in RESERVED_CONSTRAINT_KEYS:
            raise ValueError("Reserved state/system field cannot be a constraint key")
        return key

    @model_validator(mode="after")
    def validate_known_constraints(self) -> "ConstraintEntry":
        validate_known_constraint(self.key, self.value)
        return self


class SoftPreference(ConstraintEntry):
    """Same structured attribute domain as hard constraints, with soft priority."""


class ContextEntry(Schema):
    key: str
    value: StrictStr | StrictInt | StrictFloat | StrictBool | None | list[StrictStr | StrictInt | StrictFloat | StrictBool | None]


class RelativeUpdates(Schema):
    budget: Direction | None
    distance: Direction | None


class ReferenceIntent(Schema):
    rank: int | None = Field(ge=1)
    restaurant_name: str | None
    dish_name: str | None
    mention: str
    sentiment: Literal["positive", "negative", "neutral"] | None
    similar_to: bool


class StructuredPreferenceUpdate(Schema):
    set_values: SetValues
    add_hard_constraints: list[ConstraintEntry] = Field(
        description="Explicit mandatory candidate filters; extensible key/value entries, last duplicate wins"
    )
    add_soft_preferences: list[SoftPreference]
    add_semantic_preferences: list[str]
    add_negative_preferences: list[str]
    context_updates: list[ContextEntry]
    remove_preferences: list[str]
    references: list[ReferenceIntent]
    relative_updates: RelativeUpdates

    @model_validator(mode="before")
    @classmethod
    def legacy_context(cls, value):
        # Old local fixtures remain readable; the generated wire schema requires it.
        if isinstance(value, dict):
            value = dict(value)
            value.setdefault("context_updates", [])
            if isinstance(value["context_updates"], dict):
                value["context_updates"] = [{"key": k, "value": v} for k, v in value["context_updates"].items()]
        return value

    @field_validator("add_hard_constraints", mode="before")
    @classmethod
    def accept_legacy_dictionary(cls, value: object) -> object:
        """Read old wire fixtures; generated JSON Schema advertises only entries."""
        if isinstance(value, dict):
            return [{"key": key, "value": item} for key, item in value.items() if item is not None]
        return value

    def to_update(self) -> PreferenceUpdate:
        """Compatibility wrapper for the shared domain converter."""
        return llm_output_to_preference_update(self)


class FieldEvidence(Schema):
    field: str = Field(min_length=1, max_length=100, description="Domain path, e.g. food, hard_constraints.budget_max, context.meal_time")
    quote: str = Field(min_length=1, max_length=500, description="Exact supporting words from this user's current message")


class StructuredConversationTurn(Schema):
    """Internal provider projection; the shared AI1/AI3 preference schema is unchanged."""

    intent: ConversationIntent
    reply: str | None = Field(max_length=1500)
    preferences: StructuredPreferenceUpdate
    evidence: list[FieldEvidence] = Field(max_length=50)


def llm_output_to_preference_update(output: StructuredPreferenceUpdate) -> PreferenceUpdate:
    """Validate/normalize entries, then convert to public dict; last key wins.

    Revalidate model instances too, since nested lists can be mutated after parsing.
    No semantic key translation or arbitrary nested constraint values are allowed.
    """
    validated = StructuredPreferenceUpdate.model_validate(output.model_dump(mode="python"))
    return PreferenceUpdate(
        set_values=validated.set_values.model_dump(mode="json", exclude_none=True),
        add_hard_constraints={item.key: item.value for item in validated.add_hard_constraints},
        add_soft_preferences={item.key: item.value for item in validated.add_soft_preferences},
        add_semantic_preferences=validated.add_semantic_preferences,
        add_negative_preferences=validated.add_negative_preferences,
        context_updates={item.key: item.value for item in validated.context_updates},
        remove_preferences=validated.remove_preferences,
        references=[ref.model_dump(exclude_none=True) for ref in validated.references],
        relative_updates=validated.relative_updates.model_dump(exclude_none=True),
    )
