"""Explicit CatBoost YetiRank training entry point.

Training is never executed during import. Input tables must contain the
notebook's feature columns, reviewed relevance labels and session groups.
"""

from pathlib import Path
from importlib import import_module
from typing import Any

from ranking.feature_builder import FEATURE_NAMES


def train_catboost_yetirank(
	train_df: Any, valid_df: Any, *,
	features: tuple[str, ...] = FEATURE_NAMES,
	target: str = "relevance", group: str = "session_id",
	iterations: int = 700, learning_rate: float = 0.05, depth: int = 6,
	seed: int = 42, model_path: str | Path | None = None,
) -> Any:
	"""Train the notebook's CatBoost YetiRank model and optionally save it."""
	try:
		catboost = import_module("catboost")
	except ImportError as error:
		raise RuntimeError("Install the optional ai3 dependencies to train CatBoost") from error
	CatBoostRanker = catboost.CatBoostRanker
	Pool = catboost.Pool
	if iterations < 1 or learning_rate <= 0 or depth < 1:
		raise ValueError("iterations, learning_rate and depth must be positive")

	train_sorted = train_df.sort_values(group, kind="stable").reset_index(drop=True)
	valid_sorted = valid_df.sort_values(group, kind="stable").reset_index(drop=True)
	train_qid = train_sorted[group].astype(str).factorize(sort=False)[0]
	valid_qid = valid_sorted[group].astype(str).factorize(sort=False)[0]
	train_pool = Pool(train_sorted[list(features)], label=train_sorted[target], group_id=train_qid)
	valid_pool = Pool(valid_sorted[list(features)], label=valid_sorted[target], group_id=valid_qid)
	model = CatBoostRanker(
		loss_function="YetiRank", iterations=iterations,
		learning_rate=learning_rate, depth=depth, random_seed=seed, verbose=False,
	)
	model.fit(train_pool, eval_set=valid_pool, use_best_model=True)
	if model_path is not None:
		Path(model_path).parent.mkdir(parents=True, exist_ok=True)
		model.save_model(str(model_path))
	return model
