"""Small pure helpers shared by parsing and state merging."""

from collections.abc import Iterable
from typing import TypeVar
import unicodedata

T = TypeVar("T")

# Absolute values supersede pending relative requests on the same dimension.
ABSOLUTE_DIMENSIONS = (
    ("budget_max", "budget"),
    ("max_distance_km", "distance"),
)


def normalize_text(text: str) -> str:
    """Normalize Vietnamese Unicode, casing, and repeated whitespace."""
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def unique(values: Iterable[T]) -> list[T]:
    """Deduplicate in order, including unhashable JSON reference objects."""
    result: list[T] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
