"""AI 3 inference with a deterministic baseline and optional CatBoost model."""

from collections.abc import Sequence
from functools import lru_cache
import os
from pathlib import Path
from typing import Protocol

from common.schemas import Candidate, RankedResult, UserPreferenceState
from ranking.baseline_ranker import baseline_score
from ranking.feature_builder import build_feature_vector


class Ranker(Protocol):
    def score(self, state: UserPreferenceState, candidates: Sequence[Candidate]) -> list[float]: ...


DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "ranker" / "catboost_yetirank.cbm"


@lru_cache(maxsize=1)
def _load_default_ranker() -> Ranker | None:
    """Load the configured CatBoost artifact once, without import side effects."""
    model_path = Path(os.getenv("AI3_MODEL_PATH", str(DEFAULT_MODEL_PATH)))
    if not model_path.is_file():
        return None
    from ranking.model_ranker import CatBoostYetiRanker
    return CatBoostYetiRanker.from_file(model_path)


def rank_candidates(
    state: UserPreferenceState, candidates: list[Candidate], top_k: int = 10,
    *, ranker: Ranker | None = None,
) -> list[RankedResult]:
    """Rank supplied candidates, preserving IDs and exposing real features.

    When the configured CatBoost artifact exists, it is loaded lazily and used
    by default. The weighted baseline remains an offline fallback when no model
    artifact is available.
    """
    if top_k < 1:
        raise ValueError("top_k must be positive")
    if not candidates:
        return []
    selected_ranker = ranker if ranker is not None else _load_default_ranker()
    scores = (selected_ranker.score(state, candidates) if selected_ranker is not None
              else [baseline_score(state, candidate) for candidate in candidates])
    if len(scores) != len(candidates):
        raise ValueError("ranker returned a score for the wrong number of candidates")
    ranked = sorted(enumerate(zip(candidates, scores)), key=lambda item: (-float(item[1][1]), item[0]))
    results: list[RankedResult] = []
    for rank, (_, (candidate, score)) in enumerate(ranked[:top_k], 1):
        value = float(score)
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("ranker returned a non-finite score")
        features = build_feature_vector(state, candidate)
        results.append(RankedResult(
            restaurant_id=candidate.restaurant_id,
            menu_item_id=candidate.menu_item_id,
            dish_id=candidate.dish_id,
            rank=rank,
            score=value,
            restaurant_name=candidate.restaurant_name,
            dish_name=candidate.dish_name,
            price=candidate.price,
            distance_km=candidate.distance_km,
            rating=_rating(candidate),
            reason_features={
                **features,
                "ranking_model": "catboost_yetirank" if selected_ranker else "weighted_baseline",
                **({'demo_only': True} if candidate.restaurant_features.get('demo_only') else {}),
                **({'preference_evidence': candidate.match_features['preference_evidence']}
                   if 'preference_evidence' in candidate.match_features else {}),
            },
        ))
    return results


def _rating(candidate: Candidate) -> float | None:
    value = candidate.restaurant_features.get("rating")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 5:
        return float(value)
    return None
