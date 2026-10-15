"""Pure state transitions with deferred relative adjustment policies."""

from copy import deepcopy

from common.schemas import PreferenceUpdate, UserPreferenceState
from conversation._utils import unique
from conversation.context import ALIASES, normalize_context
from conversation.normalization import (
    CUISINE_ALIASES, PREFERENCE_ALIASES, SEMANTIC_ALIASES,
    canonical_constraints, canonical_values, normalize_update,
)


def update_state(
    current_state: UserPreferenceState | None,
    update: PreferenceUpdate,
    session_id: str,
    user_id: str | None = None,
) -> UserPreferenceState:
    """Apply sets, merges, removals, then relative intent to an independent snapshot.

    Removal wins over an addition in the same update. Relative events stay in the
    turn update; no numeric adjustment is invented without downstream results.
    Session/user mismatches are rejected to avoid mixing conversation identities.
    """
    if current_state is not None:
        if current_state.session_id != session_id:
            raise ValueError("current_state belongs to a different session")
        if user_id is not None and current_state.user_id not in (None, user_id):
            raise ValueError("current_state belongs to a different user")
        data = current_state.model_dump(mode="python")
        if user_id is not None:
            data["user_id"] = user_id
    else:
        data = UserPreferenceState(session_id=session_id, user_id=user_id).model_dump()

    update = normalize_update(update, current_state)
    data.update(deepcopy(update.set_values))
    # Validate replacement containers before attempting merges.
    data = UserPreferenceState.model_validate(data).model_dump(mode="python")
    data["cuisine"] = canonical_values(data["cuisine"], CUISINE_ALIASES)
    data["negative_preferences"] = canonical_values(data["negative_preferences"], PREFERENCE_ALIASES)
    data["semantic_preferences"] = canonical_values(data["semantic_preferences"], SEMANTIC_ALIASES)
    for key, value in data["context"].items():
        # Canonicalize valid legacy labels without closing custom state context
        # or reinterpreting historical nested values as new deltas.
        if key in ALIASES and (isinstance(value, str) and key != "companions"
                or key == "companions" and isinstance(value, list) and all(isinstance(v, str) for v in value)):
            data["context"][key] = normalize_context({key: value})[key]
    for scope in ("hard_constraints", "soft_preferences"):
        data[scope] = canonical_constraints(data[scope])
    for key, value in update.add_hard_constraints.items():
        if key == "allergens_excluded" and isinstance(data["hard_constraints"].get(key), list):
            data["hard_constraints"][key] = unique([*data["hard_constraints"][key], *deepcopy(value)])
        else:
            data["hard_constraints"][key] = deepcopy(value)
    data["soft_preferences"].update(deepcopy(update.add_soft_preferences))
    data["semantic_preferences"] = unique(
        [*data["semantic_preferences"], *update.add_semantic_preferences]
    )
    data["negative_preferences"] = unique(
        [*data["negative_preferences"], *update.add_negative_preferences]
    )
    data["context"].update(deepcopy(update.context_updates))
    for preference in update.remove_preferences:
        if "." in preference:
            container, key = preference.split(".", 1)
            if container in ("hard_constraints", "soft_preferences", "context"):
                data[container].pop(key, None)
                continue
        if preference in ("food", "cuisine"):
            data[preference] = []
        for field in ("semantic_preferences", "negative_preferences"):
            data[field] = [value for value in data[field] if value != preference]
        for field in ("hard_constraints", "soft_preferences"):
            data[field].pop(preference, None)

    data["reference_restaurants"] = unique(
        [*data["reference_restaurants"], *deepcopy(update.references)]
    )
    # v0.2 also purges stale events loaded from older snapshots.
    data["context"].pop("relative_updates", None)
    for key in data["hard_constraints"]:
        data["soft_preferences"].pop(key, None)

    return UserPreferenceState.model_validate(deepcopy(data))
