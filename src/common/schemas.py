"""JSON-compatible contracts shared by conversation and downstream consumers."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class Schema(BaseModel):
    """Reject misspelled fields and non-finite numeric values."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, validate_assignment=True)


class Location(Schema):
    """Geographic coordinates in decimal degrees."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class UserFormInput(Schema):
    """Explicit form values; None means no requested change."""

    location: Location | None = None
    food: str | list[str] | None = None
    cuisine: str | list[str] | None = None
    budget_max: int | None = Field(default=None, ge=0)
    max_distance_km: float | None = Field(default=None, gt=0)
    item_kind: Literal['food', 'beverage'] | None = None
    serving_style: list[Literal['dry', 'broth', 'soup', 'hotpot', 'unknown']] | None = Field(default=None, min_length=1)


class UserPreferenceState(Schema):
    """Stable preference snapshot with extensible JSON preference containers."""

    session_id: str = Field(min_length=1)
    user_id: str | None = None
    location: Location | None = None
    food: list[str] = Field(default_factory=list)
    cuisine: list[str] = Field(default_factory=list)
    hard_constraints: dict[str, JsonValue] = Field(default_factory=dict)
    soft_preferences: dict[str, JsonValue] = Field(default_factory=dict)
    semantic_preferences: list[str] = Field(default_factory=list)
    negative_preferences: list[str] = Field(default_factory=list)
    reference_restaurants: list[JsonValue] = Field(default_factory=list)
    context: dict[str, JsonValue] = Field(default_factory=dict)


PreferenceField = Literal[
    "location", "food", "cuisine", "hard_constraints", "soft_preferences",
    "semantic_preferences", "negative_preferences", "reference_restaurants", "context",
]
Direction = Literal["increase", "decrease"]


def validate_known_constraint(key: str, value: JsonValue) -> None:
    """Validate shared numeric/safety fields without closing extensible dicts."""
    if key == 'item_kind' and value not in ('food', 'beverage'):
        raise ValueError('item_kind must be food or beverage')
    if key == 'serving_style' and (not isinstance(value, list) or not value or any(v not in ('dry', 'broth', 'soup', 'hotpot', 'unknown') for v in value)):
        raise ValueError('serving_style must be a nonempty array of supported food styles')
    if key in ("budget_min", "budget_max") and (type(value) is not int or value < 0):
        raise ValueError(f"{key} must be a nonnegative integer")
    if key in ("max_distance_km", "max_travel_time_min") and (type(value) not in (int, float) or value <= 0):
        raise ValueError(f"{key} must be positive")
    if key in ("rating", "min_rating") and (type(value) not in (int, float) or not 0 <= value <= 5):
        raise ValueError(f"{key} must be between 0 and 5")
    if key in ("vegetarian", "parking", "wifi", "air_conditioning", "outdoor_seating", "wheelchair_accessible") and type(value) is not bool:
        raise ValueError(f"{key} must be boolean")
    if key == "allergens_excluded" and (not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value)):
        raise ValueError("allergens_excluded must be an array of nonempty strings")


class PreferenceUpdate(Schema):
    """Changes requested in one turn, rather than a complete state snapshot."""

    set_values: dict[PreferenceField, JsonValue] = Field(default_factory=dict)
    add_hard_constraints: dict[str, JsonValue] = Field(default_factory=dict)
    add_soft_preferences: dict[str, JsonValue] = Field(default_factory=dict)
    add_semantic_preferences: list[str] = Field(default_factory=list)
    add_negative_preferences: list[str] = Field(default_factory=list)
    context_updates: dict[str, JsonValue] = Field(default_factory=dict)
    remove_preferences: list[str] = Field(default_factory=list)
    references: list[JsonValue] = Field(default_factory=list)
    relative_updates: dict[str, Direction] = Field(default_factory=dict)

    @field_validator("add_hard_constraints", "add_soft_preferences")
    @classmethod
    def validate_constraints(cls, values):
        for key, value in values.items():
            if key in UserPreferenceState.model_fields:
                raise ValueError("State fields cannot be constraint keys")
            validate_known_constraint(key, value)
        return values

    @field_validator("set_values")
    @classmethod
    def validate_constraint_replacements(cls, values):
        for field in ("hard_constraints", "soft_preferences"):
            if isinstance(values.get(field), dict):
                cls.validate_constraints(values[field])
        context = values.get("context")
        if isinstance(context, dict):
            from conversation.context import ALIASES, normalize_context
            # Preserve legacy custom nested context, but validate known fields
            # and reject misplaced state identity/query fields on new writes.
            known = set(ALIASES) | {"party_size", "location", "food", "cuisine",
                                   "session_id", "user_id", "reference_restaurants"}
            canonical = normalize_context({k: v for k, v in context.items() if k in known})
            values["context"] = {**context, **canonical}
        return values

    @field_validator("context_updates")
    @classmethod
    def validate_context(cls, value):
        from conversation.context import normalize_context
        return normalize_context(value)


class PreviousResult(Schema):
    """A result supplied by the caller, the only source of reference IDs."""

    rank: int = Field(ge=1)
    restaurant_id: str = Field(min_length=1)
    menu_item_id: str | None = None
    restaurant_name: str | None = None
    dish_name: str | None = None


class UserRequest(Schema):
    """Input envelope for a single conversation turn."""

    session_id: str = Field(min_length=1)
    user_id: str | None = None
    form: UserFormInput = Field(default_factory=UserFormInput)
    message: str | None = None
    current_state: UserPreferenceState | None = None
    previous_results: list[PreviousResult] = Field(default_factory=list)


class Candidate(Schema):
    """AI 1 -> AI 3; IDs are opaque source identifiers, prices are VND.

    A missing menu_item_id denotes a restaurant-only candidate. distance_km
    may be absent only without a user location; price only without source data.
    Those provenance conditions are enforced by retrieval, not this envelope.
    """

    restaurant_id: str = Field(min_length=1)
    menu_item_id: str | None = Field(default=None, min_length=1)
    dish_id: str | None = Field(default=None, min_length=1)
    restaurant_name: str | None = None
    dish_name: str | None = None
    location: Location | None = None
    distance_km: float | None = Field(default=None, ge=0)
    price: int | None = Field(default=None, ge=0)
    restaurant_features: dict[str, JsonValue] = Field(default_factory=dict)
    match_features: dict[str, JsonValue] = Field(default_factory=dict)


class RankedResult(Schema):
    """AI 3 -> backend; preserve candidate IDs and explain a finite score.

    Scores are model-specific, not necessarily probabilities. Rank is one-based.
    """

    restaurant_id: str = Field(min_length=1)
    menu_item_id: str | None = Field(default=None, min_length=1)
    dish_id: str | None = Field(default=None, min_length=1)
    rank: int = Field(ge=1)
    score: float
    restaurant_name: str | None = None
    dish_name: str | None = None
    price: int | None = Field(default=None, ge=0)
    distance_km: float | None = Field(default=None, ge=0)
    rating: float | None = Field(default=None, ge=0, le=5)
    reason_features: dict[str, JsonValue] = Field(default_factory=dict)


class FeedbackEvent(Schema):
    """Backend feedback envelope; action stays open for future backend events."""

    session_id: str = Field(min_length=1)
    user_id: str | None = None
    restaurant_id: str | None = Field(default=None, min_length=1)
    menu_item_id: str | None = Field(default=None, min_length=1)
    action: str = Field(min_length=1, pattern=r"\S")
    message: str | None = None
    rank_position: int | None = Field(default=None, ge=1)


class RecommendationResponse(Schema):
    """Stable response after conversation, retrieval and ranking."""

    session_id: str = Field(min_length=1)
    state: UserPreferenceState
    results: list[RankedResult]
