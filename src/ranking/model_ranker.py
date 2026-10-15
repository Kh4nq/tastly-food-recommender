"""Optional CatBoost YetiRank adapter.

CatBoost is imported only when the adapter is constructed or trained. Importing
the ranking package therefore remains side-effect free and does not require the
optional dependency or a model artifact.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from common.schemas import Candidate, UserPreferenceState
from ranking.feature_builder import FEATURE_NAMES, build_feature_matrix


class CatBoostYetiRanker:
	"""Score Candidates with a trained CatBoost YetiRank model."""

	def __init__(self, model: Any):
		if not hasattr(model, "predict"):
			raise TypeError("model must expose predict")
		self.model = model

	@classmethod
	def from_file(cls, path: str | Path) -> "CatBoostYetiRanker":
		try:
			from catboost import CatBoostRanker
		except ImportError as error:
			raise RuntimeError("CatBoost is required to load the ranking model") from error
		model = CatBoostRanker()
		model.load_model(str(path))
		actual_features = list(getattr(model, "feature_names_", ()))
		if actual_features and actual_features != list(FEATURE_NAMES):
			raise ValueError(
				"CatBoost feature schema mismatch: "
				f"expected {list(FEATURE_NAMES)}, got {actual_features}"
			)
		return cls(model)

	def score(self, state: UserPreferenceState, candidates: Sequence[Candidate]) -> list[float]:
		if not candidates:
			return []
		values = self.model.predict(build_feature_matrix(state, candidates))
		return [float(value) for value in values]
