"""Small, exact-match ontology shared by rule, provider and state boundaries."""

from common.schemas import PreferenceUpdate, UserPreferenceState
from conversation._utils import normalize_text, unique

# A small alias vocabulary, not a closed cuisine/food taxonomy. Exact matches
# only: unknown regional cuisines and all free-text dish names stay verbatim.
CUISINE_NAMES = {
    "vietnamese": ("việt", "việt nam"),
    "korean": ("hàn", "hàn quốc"),
    "japanese": ("nhật", "nhật bản"),
    "chinese": ("trung quốc", "trung hoa", "hoa"),
    "thai": ("thái", "thái lan"),
    "italian": ("ý", "italia"),
    "western": ("tây", "phương tây"),
}
CUISINE_ALIASES = {
    alias: canonical
    for canonical, names in CUISINE_NAMES.items()
    for name in (canonical, *names)
    for alias in (name, f"đồ {name}", f"món {name}", f"ẩm thực {name}")
}
CUISINE_ALIASES.update({
    f"{canonical} {suffix}": canonical
    for canonical in CUISINE_NAMES for suffix in ("food", "cuisine")
})
# These words are also names/common Vietnamese words. A bare field value can
# normalize, but a mention inside a sentence needs an explicit cuisine phrase.
AMBIGUOUS_CUISINE_WORDS = frozenset({"việt", "hàn", "hoa", "thái", "ý", "tây", "nhật"})
SEMANTIC_PHRASES = (
    ("quán đẹp", "beautiful ambience"),
    ("chỗ chill", "relaxed ambience"),
    ("không gian phù hợp nói chuyện", "suitable for conversation"),
    ("phù hợp nói chuyện", "suitable for conversation"),
    ("yên tĩnh", "quiet"),
    ("chill", "relaxed ambience"),
)
SEMANTIC_ALIASES = {**dict(SEMANTIC_PHRASES), **{v: v for _, v in SEMANTIC_PHRASES}}
SEMANTIC_ALIASES.update({"không gian yên tĩnh": "quiet", "quiet ambience": "quiet", "quiet atmosphere": "quiet"})
PREFERENCE_ALIASES = {
    "đồ cay": "spicy", "cay": "spicy", "spicy": "spicy", "spicy food": "spicy",
    "không thích cay": "spicy", "không thích đồ cay": "spicy",
    "không ăn cay": "spicy", "không muốn ăn cay": "spicy", "đừng cay": "spicy",
    "don't like spicy food": "spicy", "i don't like spicy food": "spicy",
    "đậu phộng": "peanut", "lạc": "peanut", "peanuts": "peanut", "peanut": "peanut",
}
CONSTRAINT_VALUE_ALIASES = {
    "allergens_excluded": {"đậu phộng": "peanut", "lạc": "peanut", "peanut": "peanut", "peanuts": "peanut",
                           "hải sản": "seafood", "seafood": "seafood",
                           "hạt mè": "sesame", "mè": "sesame", "vừng": "sesame", "hạt vừng": "sesame",
                           "sesame": "sesame", "sesame seeds": "sesame",
                           "hạt điều": "cashew", "cashew": "cashew", "cashews": "cashew",
                           "cashew nuts": "cashew",
                           "quả óc chó": "walnut", "hạt óc chó": "walnut", "óc chó": "walnut",
                           "walnut": "walnut", "walnuts": "walnut",
                           "hạt dẻ cười": "pistachio", "dẻ cười": "pistachio",
                           "pistachio": "pistachio", "pistachios": "pistachio",
                           "sữa": "milk", "milk": "milk"},
}


def canonical_values(values: list[str], aliases: dict[str, str]) -> list[str]:
    """Preserve unknown text verbatim; deduplicate after exact alias lookup."""
    return unique(aliases.get(normalize_text(value), value) for value in values)


def canonical_constraints(values: dict) -> dict:
    """Normalize only established list-valued aliases; do not coerce booleans,
    translate extensible keys, or invent enums for dietary/service attributes.
    """
    result = dict(values)
    for key, aliases in CONSTRAINT_VALUE_ALIASES.items():
        value = result.get(key)
        if isinstance(value, list) and all(isinstance(v, str) for v in value):
            result[key] = canonical_values(value, aliases)
    return result


def normalize_update(update: PreferenceUpdate, current_state: UserPreferenceState | None = None) -> PreferenceUpdate:
    """Canonicalize known exact aliases; preserve unknown/free-text values."""
    # validate_assignment does not cover mutation inside a dict/list.
    result = PreferenceUpdate.model_validate(update.model_dump(mode="python"))
    for scope in ("hard_constraints", "soft_preferences"):
        setattr(result, "add_" + scope, canonical_constraints(getattr(result, "add_" + scope)))
        if isinstance(result.set_values.get(scope), dict):
            result.set_values[scope] = canonical_constraints(result.set_values[scope])
    for field, aliases in (("cuisine", CUISINE_ALIASES),
                           ("semantic_preferences", SEMANTIC_ALIASES),
                           ("negative_preferences", PREFERENCE_ALIASES)):
        values = result.set_values.get(field)
        # Invalid containers must still be rejected by the existing validation.
        if isinstance(values, list) and all(isinstance(v, str) for v in values):
            result.set_values[field] = canonical_values(values, aliases)
    result.add_negative_preferences = canonical_values(result.add_negative_preferences, PREFERENCE_ALIASES)
    result.add_semantic_preferences = canonical_values(result.add_semantic_preferences, SEMANTIC_ALIASES)
    result.remove_preferences = canonical_values(
        result.remove_preferences, {**SEMANTIC_ALIASES, **PREFERENCE_ALIASES})
    paths = []
    for key in result.remove_preferences:
        if key in ("budget_max", "budget_min", "max_distance_km", "max_travel_time_min"):
            scopes = []
            for scope in ("hard_constraints", "soft_preferences"):
                replacement = result.set_values.get(scope, {})
                existing = getattr(current_state, scope, {})
                if (key in existing or key in getattr(result, "add_" + scope)
                        or isinstance(replacement, dict) and key in replacement):
                    scopes.append(scope)
            paths.extend(scope + "." + key for scope in scopes or ["hard_constraints"])
        else:
            paths.append(key)
    result.remove_preferences = unique(paths)
    # Apply removals before hard/soft and absolute/relative conflict cleanup.
    for path in result.remove_preferences:
        if path in ("food", "cuisine"):
            result.set_values.pop(path, None)
        container, separator, leaf = path.partition(".")
        if separator and container in ("hard_constraints", "soft_preferences", "context"):
            addition = "context_updates" if container == "context" else "add_" + container
            getattr(result, addition).pop(leaf, None)
            replacement = result.set_values.get(container)
            if isinstance(replacement, dict):
                replacement.pop(leaf, None)
            continue
        for scope in ("hard_constraints", "soft_preferences"):
            getattr(result, "add_" + scope).pop(path, None)
            replacement = result.set_values.get(scope)
            if isinstance(replacement, dict):
                replacement.pop(path, None)
        for scope in ("semantic_preferences", "negative_preferences"):
            setattr(result, "add_" + scope, [v for v in getattr(result, "add_" + scope) if v != path])
            replacement = result.set_values.get(scope)
            if isinstance(replacement, list):
                result.set_values[scope] = [v for v in replacement if v != path]
    for field, values in result.set_values.items():
        if isinstance(values, list):
            result.set_values[field] = unique(values)
    # Absolute evidence wins over same-turn relative interpretation.
    replacement = result.set_values.get("hard_constraints", {})
    hard = {**replacement, **result.add_hard_constraints} if isinstance(replacement, dict) else result.add_hard_constraints
    soft = result.set_values.get("soft_preferences", {})
    for key in hard:
        result.add_soft_preferences.pop(key, None)
        if isinstance(soft, dict):
            soft.pop(key, None)
    for dimension, keys in (("budget", ("budget_min", "budget_max")),
                            ("distance", ("max_distance_km", "max_travel_time_min"))):
        absolute = {**(soft if isinstance(soft, dict) else {}), **result.add_soft_preferences, **hard}
        if any(key in absolute for key in keys):
            result.relative_updates.pop(dimension, None)
    return result
