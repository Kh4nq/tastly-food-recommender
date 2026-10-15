"""Resolve ordinals/names against caller-owned results, never generate IDs."""

import re
from types import MappingProxyType

from common.schemas import PreviousResult
from conversation._utils import normalize_text, unique

ORDINALS = MappingProxyType({"nhất": 1, "một": 1, "hai": 2, "ba": 3, "tư": 4, "bốn": 4, "năm": 5})
REFERENCE_PATTERN = re.compile(
    r"\b(?:quán|cái|món)(?:\s+(?:thứ|số))?\s+(đầu tiên|nhất|một|hai|ba|tư|bốn|năm|\d+|này|đó)\b"
)


def resolve_selector(selector: dict, results: list[PreviousResult]) -> dict:
    """Ambiguous, missing or conflicting selectors remain unresolved."""
    candidates = list(results)
    filters = []
    for key in ("rank", "restaurant_name", "dish_name", "restaurant_id", "menu_item_id"):
        value = selector.get(key)
        if value is not None:
            filters.append(key)
            candidates = [r for r in candidates if (
                normalize_text(str(getattr(r, key))) == normalize_text(str(value))
            )]
    mention = selector.get("mention")
    if isinstance(mention, str):
        match = REFERENCE_PATTERN.search(normalize_text(mention))
        if match:
            token = match[1]
            rank = 1 if token == "đầu tiên" else ORDINALS.get(token)
            if token.isdigit():
                rank = int(token)
            if rank is not None:
                candidates = [r for r in candidates if r.rank == rank]
                filters.append("rank")
    if not filters or len(candidates) != 1:
        # Do not echo an untrusted ID even in an unresolved object.
        return {"status": "unresolved", "mention": str(mention or "unresolved reference")}
    result = candidates[0]
    resolved = {"status": "resolved", "rank": result.rank, "restaurant_id": result.restaurant_id}
    if result.menu_item_id is not None:
        resolved["menu_item_id"] = result.menu_item_id
    if isinstance(mention, str):
        resolved["mention"] = mention
    if selector.get("sentiment") in ("positive", "negative", "neutral"):
        resolved["sentiment"] = selector["sentiment"]
    if selector.get("similar_to") is True:
        resolved["similar_to"] = result.restaurant_id
    return resolved


def resolve_message_references(message: str, results: list[PreviousResult]) -> list[dict]:
    """Resolve explicit references only; feedback meaning is left to the LLM."""
    text = normalize_text(message)
    selectors = []
    for match in REFERENCE_PATTERN.finditer(text):
        if not results and match[0] in {"món đó", "món này"}:
            # With no previous recommendations, a recognized food/dislike
            # already stated in this utterance is not a restaurant selector.
            # If caller results exist, retain the ambiguity for inference.
            from conversation.rule_parser import parse_by_rules_detailed
            antecedent = parse_by_rules_detailed(text[:match.start()]).update
            if antecedent.set_values.get("food") or antecedent.add_negative_preferences:
                continue
        selectors.append({"mention": match[0]})
    for result in results:
        for key, prefix in (("restaurant_name", "quán"), ("dish_name", "món")):
            name = getattr(result, key)
            if name and re.search(rf"\b{prefix}\s+{re.escape(normalize_text(name))}\b", text):
                selectors.append({key: name, "mention": f"{prefix} {name}"})
    # Preserve an unknown named restaurant without guessing its ID.
    if not selectors:
        match = re.search(r"\bquán\s+([A-ZĐ][\w-]*(?:\s+[A-ZĐ][\w-]*)*)", message)
        if match:
            selectors.append({"mention": match[0]})
    return merge_references([], [resolve_selector(selector, results) for selector in selectors])


def resolve_llm_references(references: list, results: list[PreviousResult], message: str | None = None) -> list[dict]:
    selectors = [ref if isinstance(ref, dict) else {"mention": ref} for ref in references]
    resolved = [resolve_selector(ref, results) for ref in selectors]
    if message is not None:
        grounded = resolve_message_references(message, results)
        residue = normalize_text(message)
        for ref in grounded:
            residue = residue.replace(normalize_text(ref.get("mention", "")), " ")
        numeric_feedback_only = re.fullmatch(r"\s*(?:rẻ hơn|giá thấp hơn|gần hơn)(?: nhé| nha| đi)*[.!? ]*", residue)
        for selector, ref in zip(selectors, resolved):
            source = next((r for r in grounded if r.get("status") == "resolved"
                           and r.get("restaurant_id") == ref.get("restaurant_id")
                           and r.get("menu_item_id") == ref.get("menu_item_id")), None)
            if source is None:
                for candidate in grounded:
                    match = REFERENCE_PATTERN.fullmatch(normalize_text(candidate["mention"]))
                    token = match[1] if match else None
                    rank = int(token) if token and token.isdigit() else 1 if token == "đầu tiên" else ORDINALS.get(token)
                    if rank is not None and str(selector.get("rank")) == str(rank):
                        source = candidate
                        break
            if source:
                ref["mention"] = source["mention"]
            elif (not selector.get("mention") or normalize_text(str(selector["mention"])) not in normalize_text(message)):
                ref.clear()
                ref.update(status="unresolved", mention="unresolved reference")
            if numeric_feedback_only:
                ref.pop("sentiment", None)
                ref.pop("similar_to", None)
    return unique(resolved)


def merge_references(deterministic: list[dict], inferred: list[dict]) -> list[dict]:
    """Enrich the same result with sentiment instead of duplicating it."""
    merged = []
    for ref in [*deterministic, *inferred]:
        if ref.get("status") == "unresolved" and any(
            r.get("status") == "resolved" and normalize_text(r.get("mention", "")) == normalize_text(ref.get("mention", ""))
            for r in merged
        ):
            continue  # Conflicting inference cannot downgrade a caller-grounded reference.
        existing = next((r for r in merged if r.get("status") == "resolved"
                         and ref.get("status") == "resolved"
                         and r.get("restaurant_id") == ref.get("restaurant_id")
                         and r.get("menu_item_id") == ref.get("menu_item_id")), None)
        if existing is None and ref.get("status") == "unresolved":
            existing = next((r for r in merged if r.get("status") == "unresolved"
                             and normalize_text(r.get("mention", "")) == normalize_text(ref.get("mention", ""))), None)
        if existing is not None:
            existing.update(ref)
        elif ref not in merged:
            merged.append(dict(ref))
    return merged
