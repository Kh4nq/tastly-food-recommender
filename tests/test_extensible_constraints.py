"""Extensible structured constraints, shared conversion and offline adapters."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from common.schemas import PreferenceUpdate, UserPreferenceState, UserRequest
from conversation import process_user_request, update_state
from conversation.prompts import SYSTEM_PROMPT
from conversation.providers import MockProvider
from conversation.providers.gemini_provider import GeminiProvider
from conversation.providers.openai_provider import OpenAIProvider
from conversation.providers.structured import (
    ConstraintEntry, RESERVED_CONSTRAINT_KEYS, StructuredPreferenceUpdate,
    llm_output_to_preference_update,
)


def make_output(entries: list[dict], *, soft: list[dict] | None = None) -> StructuredPreferenceUpdate:
    return StructuredPreferenceUpdate.model_validate({
        "set_values": {"food": ["ramen"], "cuisine": None, "location": None},
        "add_hard_constraints": entries,
        "add_soft_preferences": soft or [],
        "add_semantic_preferences": [], "add_negative_preferences": [],
        "remove_preferences": [], "references": [],
        "relative_updates": {"budget": None, "distance": None},
    })


@pytest.mark.parametrize("constraints", [
    {"budget_max": 150000, "max_distance_km": 3},
    {"parking": True}, {"allergen_free": "peanut"},
    {"parking": True, "halal": True, "air_conditioning": True},
    {"outdoor_seating": True, "wheelchair_accessible": True, "private_room": True, "accepts_card": True},
    {"unknown_new_feature": ["a", "b"]}, {"unknown_new_feature": 12},
    {"unknown_new_feature": 1.25}, {"unknown_new_feature": False},
])
def test_extensible_constraint_types_and_public_dict(constraints):
    output = make_output([{"key": key, "value": value} for key, value in constraints.items()])
    update = llm_output_to_preference_update(output)
    assert isinstance(update.add_hard_constraints, dict)
    assert update.add_hard_constraints == constraints
    for key, value in constraints.items():
        assert type(update.add_hard_constraints[key]) is type(value)
    current = UserPreferenceState(session_id="S", hard_constraints={"existing_feature": True})
    state = update_state(current, update, "S")
    assert state.hard_constraints == {"existing_feature": True, **constraints}
    assert current.hard_constraints == {"existing_feature": True}
    assert StructuredPreferenceUpdate.model_validate_json(output.model_dump_json()) == output
    assert PreferenceUpdate.model_validate_json(update.model_dump_json()) == update
    assert UserPreferenceState.model_validate_json(state.model_dump_json()) == state


def test_key_normalization_duplicate_last_wins_without_translation():
    output = make_output([
        {"key": " Parking ", "value": True},
        {"key": "PARKING", "value": False},
        {"key": "bãi đỗ xe", "value": True},
    ])
    assert output.to_update().add_hard_constraints == {"parking": False, "bãi đỗ xe": True}


@pytest.mark.parametrize("key", sorted(RESERVED_CONSTRAINT_KEYS))
def test_reserved_key_rejected_after_normalization(key):
    with pytest.raises(ValidationError, match="Reserved"):
        make_output([{"key": f" {key.upper()} ", "value": "BAD"}])


@pytest.mark.parametrize("key", ["", "  ", "\n\t"])
def test_empty_key_rejected(key):
    with pytest.raises(ValidationError, match="empty"):
        make_output([{"key": key, "value": True}])


@pytest.mark.parametrize("value", [None, {"nested": True}, [1, 2], [True], [["peanut"]],
                                  float("nan"), float("inf"), float("-inf")])
def test_unsupported_constraint_value_rejected(value):
    with pytest.raises(ValidationError):
        make_output([{"key": "feature", "value": value}])


@pytest.mark.parametrize("key,value", [
    ("budget_max", -1), ("budget_max", 1.5), ("budget_max", True),
    ("max_distance_km", 0), ("max_distance_km", -2),
    ("vegetarian", "true"), ("rating", 6),
])
def test_existing_business_validation_preserved(key, value):
    with pytest.raises(ValidationError):
        make_output([{"key": key, "value": value}])


def test_wire_schema_advertises_entries_not_a_feature_registry():
    schema = StructuredPreferenceUpdate.model_json_schema()
    hard = schema["properties"]["add_hard_constraints"]
    assert hard["type"] == "array"
    assert hard["items"] == {"$ref": "#/$defs/ConstraintEntry"}
    entry = schema["$defs"]["ConstraintEntry"]
    assert entry["additionalProperties"] is False
    assert set(entry["properties"]) == {"key", "value"}
    assert "enum" not in entry["properties"]["key"]
    assert {item["type"] for item in entry["properties"]["value"]["anyOf"]} == {
        "string", "integer", "number", "boolean", "array",
    }


def test_converter_revalidates_mutated_entries_and_does_not_alias():
    output = make_output([{"key": "allergen_free", "value": ["peanut"]}])
    update = output.to_update()
    update.add_hard_constraints["allergen_free"].append("milk")
    assert output.add_hard_constraints[0].value == ["peanut"]
    output.add_hard_constraints.append(ConstraintEntry.model_construct(key="session_id", value="BAD"))
    with pytest.raises(ValidationError, match="Reserved"):
        output.to_update()


def test_end_to_end_structured_mock_custom_hard_constraints():
    message = "Tìm quán ramen dưới 150k, bắt buộc có chỗ đậu xe và không có đậu phộng."
    output = make_output([
        {"key": "budget_max", "value": 150000},
        {"key": "parking", "value": True},
        {"key": "allergen_free", "value": "peanut"},
    ])
    before = output.model_dump()
    provider = MockProvider({message: output})
    result = process_user_request(UserRequest(session_id="S", message=message), provider)
    assert provider.call_count == 1
    assert result.metadata.parser_used == "hybrid_llm"
    assert not result.metadata.partial_result
    assert result.state.food == ["ramen"]
    assert result.state.hard_constraints == {
        "budget_max": 150000, "parking": True, "allergen_free": "peanut",
    }
    assert output.model_dump() == before


def test_soft_parking_fixture_remains_soft_and_prompt_teaches_distinction():
    message = "có chỗ đậu xe thì tốt"
    output = make_output([], soft=[{"key": "parking", "value": True}])
    output.set_values.food = None
    provider = MockProvider(callback=lambda **kwargs: output)
    result = process_user_request(UserRequest(session_id="S", message=message), provider)
    assert provider.call_count == 0  # v0.2 resolves explicit soft parking by rule.
    assert result.state.hard_constraints == {}
    assert result.state.soft_preferences == {"parking": True}
    assert "'phải có chỗ đậu xe' -> add_hard_constraints" in SYSTEM_PROMPT
    assert "'có chỗ đậu xe thì tốt' -> add_soft_preferences" in SYSTEM_PROMPT
    assert "NOT an exhaustive list" in SYSTEM_PROMPT


@pytest.mark.parametrize("provider_type", [OpenAIProvider, GeminiProvider])
@pytest.mark.parametrize("reserved", [False, True])
def test_real_adapters_share_extensible_conversion_offline(provider_type, reserved):
    output = make_output([
        {"key": " Parking ", "value": True},
        {"key": "allergen_free", "value": "peanut"},
    ])
    # Simulate SDK success or an invalid response bypassing SDK validation.
    payload = output.model_dump()
    if reserved:
        payload["add_hard_constraints"].append({"key": "session_id", "value": "BAD"})
    provider = provider_type.__new__(provider_type)
    provider.model = "fake-model"
    if provider_type is OpenAIProvider:
        endpoint = Mock(return_value=SimpleNamespace(output_parsed=payload))
        provider._client = SimpleNamespace(responses=SimpleNamespace(parse=endpoint))
    else:
        endpoint = Mock(return_value=SimpleNamespace(text=json.dumps(payload)))
        provider._client = SimpleNamespace(models=SimpleNamespace(generate_content=endpoint))
    # Keep an unparsed semantic intent so this adapter test still reaches the
    # fake SDK now that the seafood allergy is understood deterministically.
    result = process_user_request(UserRequest(session_id="S", message="ramen dưới 150k, phải có chỗ đậu xe, dị ứng hải sản, ánh sáng dịu"), provider)
    endpoint.assert_called_once()
    assert result.state.session_id == "S"
    if reserved:
        assert result.metadata.partial_result
        assert result.metadata.llm_error == "invalid_output"
        assert result.state.hard_constraints == {"budget_max": 150000, "parking": True, "allergens_excluded": ["seafood"]}
    else:
        assert not result.metadata.partial_result
        assert result.state.hard_constraints == {
            "budget_max": 150000, "parking": True, "allergen_free": "peanut", "allergens_excluded": ["seafood"],
        }
