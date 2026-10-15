"""Build the numeric feature vector used by the AI 3 rankers.

The feature names and order mirror ``mlai_restaurant_ranker_v4.ipynb``.  AI 1
may provide precomputed match features; the builder derives simple ratios and
exact dish-cuisine matches from shared evidence when those values are absent.
"""

from collections.abc import Sequence
from math import isfinite
from typing import Any

from common.schemas import Candidate, UserPreferenceState


FEATURE_NAMES = (
	"distance_km", "price_ratio", "budget_fit", "distance_ratio",
	"category_match", "protein_match", "cooking_match", "cuisine_match",
	"meal_category_score", "calorie_fit", "calorie_ratio",
	"food_match", "semantic_similarity", "dish_similarity", "restaurant_similarity",
)

FEATURE_SCHEMA_VERSION = "ai3-v3-15"

# Matches meal_score in mlai-food/scripts/27-build-ranking-training-data-v3.py.
MEAL_CATEGORY_SCORES = {
    'breakfast': {'bakery': 1.0, 'noodle': .9, 'rice': .75, 'soup': .8,
                  'beverage': .8, 'main_dish': .65, 'snack': .6},
    'lunch': {'main_dish': 1.0, 'rice': 1.0, 'noodle': .95, 'soup': .8,
              'salad': .75, 'hotpot': .65},
    'dinner': {'main_dish': 1.0, 'hotpot': 1.0, 'rice': .9, 'noodle': .9,
               'soup': .8, 'salad': .75},
    'snack': {'snack': 1.0, 'dessert': 1.0, 'bakery': .95, 'beverage': .9, 'salad': .5},
}


def _label(value):
    if not isinstance(value, str):
        return None
    value = value.strip().casefold()
    return value if value not in {'', 'unknown', 'other', 'none', 'null', 'nan'} else None


def _metadata(candidate, key):
    return candidate.match_features.get(key, candidate.restaurant_features.get(key))


def _requested_labels(state, *keys):
    for container in (state.hard_constraints, state.soft_preferences):
        for key in keys:
            value = container.get(key)
            values = value if isinstance(value, list) else [value]
            labels = {_label(v) for v in values} - {None}
            if labels:
                return labels
    return set()


def _metadata_features(state, candidate):
    values = {}
    for name, column, aliases in (
        ('category_match', 'primary_category', ('preferred_category', 'primary_category', 'category')),
        ('protein_match', 'main_protein', ('preferred_protein', 'main_protein', 'protein')),
        ('cooking_match', 'primary_cooking_style', ('preferred_cooking_style', 'primary_cooking_style', 'cooking_style')),
    ):
        actual = _label(_metadata(candidate, column))
        wanted = _requested_labels(state, *aliases)
        values[name] = float(actual is not None and actual in wanted)
    category = _label(_metadata(candidate, 'primary_category'))
    meal = _label(state.context.get('meal_time'))
    values['meal_category_score'] = (
        MEAL_CATEGORY_SCORES[meal].get(category, .35)
        if meal in MEAL_CATEGORY_SCORES and category is not None else 0.0
    )
    calories = _metadata(candidate, 'calories')
    has_calories = (isinstance(calories, (int, float)) and not isinstance(calories, bool)
                    and isfinite(calories) and calories >= 0)
    limit = _constraint(state, 'calorie_limit', 'calories_max', 'max_calories')
    if not has_calories or (limit is not None and limit <= 0):
        values.update(calorie_fit=0.0, calorie_ratio=0.0)
    elif limit is None:
        # Same neutral no-limit encoding as the V3 training data, with real metadata.
        values.update(calorie_fit=1.0, calorie_ratio=1.0)
    else:
        ratio = float(calories) / limit
        values.update(calorie_ratio=ratio, calorie_fit=max(0.0, min(1.0, 1.0 - max(ratio - 1.0, 0.0))))
    return values


def _number(value: Any, default: float = 0.0) -> float:
	"""Return a finite numeric feature value, treating unknown data as zero."""
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		return default
	result = float(value)
	return result if isfinite(result) else default


def _lookup(candidate: Candidate, name: str) -> float | None:
	for container in (candidate.match_features, candidate.restaurant_features):
		if name in container:
			return _number(container[name])
	return None


def _constraint(state: UserPreferenceState, *names: str) -> float | None:
	for name in names:
		value = state.hard_constraints.get(name)
		if value is None:
			value = state.soft_preferences.get(name)
		if value is not None:
			return _number(value)
	return None


def _dish_cuisine_match(state: UserPreferenceState, candidate: Candidate) -> float:
	"""Match explicit labels only; do not infer aliases or cuisine from names."""
	cuisine = candidate.match_features.get("dish_supported_cuisine")
	if not isinstance(cuisine, str):
		return 0.0
	cuisine = cuisine.strip().casefold()
	if cuisine in {"", "unknown", "other", "none", "null", "nan"}:
		return 0.0
	return float(any(value.strip().casefold() == cuisine for value in state.cuisine))


def build_feature_vector(state: UserPreferenceState, candidate: Candidate) -> dict[str, float]:
	"""Build one deterministic feature vector for a Candidate.

	Missing numeric values use ``0.0``.  For derived ratios, an unavailable
	denominator produces ``0.0`` rather than pretending that the candidate
	fits the preference.
	"""
	budget = _constraint(state, "budget_max")
	max_distance = _constraint(state, "max_distance_km")
	distance = _lookup(candidate, "distance_km")
	if distance is None:
		distance = candidate.distance_km
	price = _lookup(candidate, "price")
	if price is None and candidate.price is not None:
		price = float(candidate.price)

	price_ratio = _lookup(candidate, "price_ratio")
	has_price_evidence = price_ratio is not None or price is not None
	if price_ratio is None:
		price_ratio = price / budget if price is not None and budget is not None and budget > 0 else 0.0
	budget_fit = _lookup(candidate, "budget_fit")
	if budget_fit is None:
		budget_fit = (max(0.0, 1.0 - price_ratio)
					  if has_price_evidence and budget is not None and budget > 0 else 0.0)

	distance_ratio = _lookup(candidate, "distance_ratio")
	if distance_ratio is None:
		distance_ratio = distance / max_distance if distance is not None and max_distance else 0.0

	values: dict[str, float] = {
		"distance_km": _number(distance),
		"price_ratio": _number(price_ratio),
		"budget_fit": _number(budget_fit),
		"distance_ratio": _number(distance_ratio),
	}
	derived = _metadata_features(state, candidate)
	for name in FEATURE_NAMES[4:]:
		value = _lookup(candidate, name)
		if name == "cuisine_match" and value is None:
			value = _dish_cuisine_match(state, candidate)
		elif value is None and name in derived:
			value = derived[name]
		values[name] = _number(value)
	return values


def build_feature_matrix(
	state: UserPreferenceState, candidates: Sequence[Candidate],
) -> list[list[float]]:
	"""Return rows in the exact feature order expected by CatBoost."""
	return [[vector[name] for name in FEATURE_NAMES]
			for vector in (build_feature_vector(state, candidate) for candidate in candidates)]
