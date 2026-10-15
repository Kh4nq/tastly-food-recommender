"""Deterministic weighted baseline matching the notebook heuristic."""

from collections.abc import Sequence

from common.schemas import Candidate, UserPreferenceState
from ranking.feature_builder import build_feature_vector


BASELINE_WEIGHTS = {
	"food_match": 0.4,
	"semantic_similarity": 0.3,
	"dish_similarity": 0.2,
	"restaurant_similarity": 0.1,
}


def baseline_score(state: UserPreferenceState, candidate: Candidate) -> float:
	"""Return the 15-feature notebook's hand-computable score."""
	features = build_feature_vector(state, candidate)
	return (
		sum(BASELINE_WEIGHTS[name] * features[name] for name in BASELINE_WEIGHTS)
	)


def rank_with_baseline(
	state: UserPreferenceState, candidates: Sequence[Candidate],
) -> list[tuple[Candidate, float]]:
	"""Score candidates, using stable input order to resolve equal scores."""
	scored = [(candidate, baseline_score(state, candidate)) for candidate in candidates]
	return sorted(scored, key=lambda item: item[1], reverse=True)
