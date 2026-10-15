"""Offline ranking metrics used by the notebook and model reports."""

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from math import log2
from typing import Any


def _dcg(values: Sequence[float], k: int) -> float:
	return sum((2 ** value - 1) / log2(index + 2)
			   for index, value in enumerate(values[:k]))


def ndcg_at_k(labels: Sequence[float], scores: Sequence[float], k: int) -> float:
	order = sorted(range(len(scores)), key=lambda index: (-scores[index], index))
	predicted = [labels[index] for index in order]
	ideal = sorted(labels, reverse=True)
	denominator = _dcg(ideal, k)
	return _dcg(predicted, k) / denominator if denominator else 0.0


def reciprocal_rank(labels: Sequence[float], scores: Sequence[float], threshold: float = 2) -> float:
	order = sorted(range(len(scores)), key=lambda index: (-scores[index], index))
	for position, index in enumerate(order, 1):
		if labels[index] >= threshold:
			return 1.0 / position
	return 0.0


def recall_at_k(labels: Sequence[float], scores: Sequence[float], k: int, threshold: float = 2) -> float:
	relevant = {index for index, label in enumerate(labels) if label >= threshold}
	if not relevant:
		return 0.0
	order = sorted(range(len(scores)), key=lambda index: (-scores[index], index))
	return len(relevant.intersection(order[:k])) / len(relevant)


def evaluate_ranking(
	rows: Iterable[Mapping[str, Any]], scores: Sequence[float], *,
	group: str = "session_id", target: str = "relevance",
	ks: Sequence[int] = (5, 10), relevance_threshold: float = 2,
) -> dict[str, float]:
	"""Return mean NDCG, MRR and Recall across query/session groups.

	``rows`` must be in the same order as ``scores``. Labels are expected to be
	reviewed relevance values, not model predictions.
	"""
	materialized = list(rows)
	if len(materialized) != len(scores):
		raise ValueError("rows and scores must have the same length")
	grouped: dict[Any, list[tuple[float, float]]] = defaultdict(list)
	for row, score in zip(materialized, scores):
		grouped[row[group]].append((float(row[target]), float(score)))
	if not grouped:
		return {f"ndcg@{k}": 0.0 for k in ks} | {"mrr": 0.0} | {f"recall@{max(ks, default=0)}": 0.0}
	summary: dict[str, float] = {}
	for k in ks:
		summary[f"ndcg@{k}"] = sum(ndcg_at_k([x[0] for x in values], [x[1] for x in values], k)
									for values in grouped.values()) / len(grouped)
		summary[f"recall@{k}"] = sum(recall_at_k([x[0] for x in values], [x[1] for x in values], k, relevance_threshold)
									  for values in grouped.values()) / len(grouped)
	summary["mrr"] = sum(reciprocal_rank([x[0] for x in values], [x[1] for x in values], relevance_threshold)
						  for values in grouped.values()) / len(grouped)
	return summary
