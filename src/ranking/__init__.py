"""AI 3 public entry point; importing never loads weights or starts training."""

from ranking.predict import rank_candidates

__all__ = ["rank_candidates"]
