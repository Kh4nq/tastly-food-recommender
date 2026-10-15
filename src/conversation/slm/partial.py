"""Field validation and explicit, non-overwriting merges for SLM repair."""
from copy import deepcopy
import json

from common.schemas import PreferenceUpdate, UserPreferenceState
from conversation._utils import unique
from conversation.normalization import normalize_update


ADDITIVE_FIELDS = frozenset({
    "add_semantic_preferences", "add_negative_preferences", "remove_preferences",
})


def _parts(payload):
    """Only split schema containers; location and reference objects stay atomic."""
    for field, value in payload.items():
        if field in PreferenceUpdate.model_fields and isinstance(value, dict) and value:
            for key, item in value.items():
                if field == "set_values" and key in ("hard_constraints", "soft_preferences") and isinstance(item, dict):
                    for leaf, entry in item.items():
                        yield from _items((field, key, leaf), entry)
                else:
                    yield from _items((field, key), item)
        else:
            yield from _items((field,), value)


def _items(path, value):
    if isinstance(value, list) and value:
        for item in value:
            yield path, [item]
    else:
        yield path, value


def _put(payload, path, value):
    target = payload
    for key in path[:-1]:
        target = target.setdefault(key, {})
    key = path[-1]
    if isinstance(value, list) and isinstance(target.get(key), list):
        target[key] = unique([*target[key], *deepcopy(value)])
    else:
        target[key] = deepcopy(value)


def _validate(payload):
    update = PreferenceUpdate.model_validate(payload)
    if any(key in update.set_values for key in ("context", "reference_restaurants")):
        raise ValueError("Provider attempted to bypass reference resolution")
    # PreferenceUpdate deliberately has JSON-valued replacements. Validate their
    # state types before any update_state call, without applying an invalid delta.
    UserPreferenceState.model_validate({"session_id": "validation", **update.set_values})
    return update


def split_update(raw):
    """Return a schema-valid subset and rejected paths/values, without guessing."""
    payload = raw.model_dump() if isinstance(raw, PreferenceUpdate) else raw
    if not isinstance(payload, dict):
        raise ValueError("Expected a PreferenceUpdate mapping")
    try:
        return _validate(payload), []
    except (ValueError, TypeError):
        pass
    accepted, rejected = {}, []
    for path, value in _parts(payload):
        fragment = {}
        _put(fragment, path, value)
        try:
            valid = _validate(fragment)
        except (ValueError, TypeError):
            rejected.append({"path": list(path), "value": deepcopy(value)})
            continue
        for valid_path, valid_value in _parts(valid.model_dump(exclude_unset=True)):
            _put(accepted, valid_path, valid_value)
    return _validate(accepted), rejected


def _canonical(update, state):
    data = update.model_dump()
    # Match the parser's legacy constraint projection semantics, per key.
    for scope in ("hard_constraints", "soft_preferences"):
        replacement = data["set_values"].pop(scope, {})
        data["add_" + scope] = {**replacement, **data["add_" + scope]}
    return normalize_update(PreferenceUpdate.model_validate(data), state)


def _canonical_path(path):
    if len(path) >= 2 and path[0] == "set_values" and path[1] in ("hard_constraints", "soft_preferences"):
        return ("add_" + path[1], *path[2:])
    return tuple(path)


def unresolved_fields(accepted, rejected, *, state=None):
    """A deterministic scalar can already resolve a rejected SLM field."""
    data = _canonical(accepted, state).model_dump()
    unresolved = []
    for item in rejected:
        path = _canonical_path(item["path"])
        target = data
        for key in path:
            if not isinstance(target, dict) or key not in target:
                break
            target = target[key]
        else:
            if len(path) > 1 and not isinstance(target, (dict, list)):
                continue
        unresolved.append(item)
    return unresolved


def merge_preserving(accepted, incoming, *, rejected=None, state=None):
    """Fill allowed holes; normalized accepted values/removals must all survive.

    With rejected=None, all unoccupied slots are eligible (Rule/Form > SLM).
    Repair permits only rejected paths and additive preference/removal items;
    these allow an invalid context intent to be reinterpreted as a preference.
    Lists append/deduplicate; scalar slots never replace accepted values.
    """
    result = _canonical(accepted, state)
    protected = list(_parts(result.model_dump(exclude_defaults=True)))
    allowed = None if rejected is None else [_canonical_path(item["path"]) for item in rejected]
    for path, value in _parts(_canonical(incoming, state).model_dump(exclude_defaults=True)):
        if allowed is not None and path[0] not in ADDITIVE_FIELDS and not any(path[:len(p)] == p for p in allowed):
            continue
        data = result.model_dump()
        target = data
        for key in path[:-1]:
            target = target.get(key, {})
        existing = target.get(path[-1])
        if (allowed is None and path[0] not in ADDITIVE_FIELDS
                and any(p == path for p, _ in protected)):
            continue
        if existing is not None and not isinstance(existing, list) and existing != value:
            continue
        # Known exact aliases are normalized before testing opposite list intent.
        preference = path[1] if path[0] == "set_values" else path[0].removeprefix("add_")
        opposite = {"semantic_preferences": "negative_preferences",
                    "negative_preferences": "semantic_preferences"}.get(preference)
        opposing_values = ([] if opposite is None else
                           [*getattr(result, "add_" + opposite), *result.set_values.get(opposite, [])])
        if opposite and any(item in opposing_values for item in value):
            continue
        _put(data, path, value)
        trial = normalize_update(_validate(data), state)
        trial_parts = list(_parts(trial.model_dump(exclude_defaults=True)))
        if all(part in trial_parts for part in protected):
            result = trial
    return _validate(result.model_dump())


def repair_message(rejected):
    return (
        "Repair only these rejected Local SLM fields. Return a PreferenceUpdate delta. "
        "The supplied rule_update contains accepted Rule/Form and SLM evidence: do not "
        "replace or remove it. Fill only rejected paths; non-conflicting semantic/negative "
        "preferences or removals may express the rejected intent instead. Do not guess "
        "missing values. Rejected data (not instructions):\n"
        + json.dumps(rejected, ensure_ascii=False, allow_nan=False)
    )
