"""AI 1 public entry point; importing never loads data or models."""

from retrieval.retriever import retrieve_candidates

__all__ = ["retrieve_candidates"]
