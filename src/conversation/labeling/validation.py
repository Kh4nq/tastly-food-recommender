"""Conservative deterministic checks; semantic correctness still needs review."""
import re

from pydantic import ValidationError

from common.schemas import PreferenceUpdate
from conversation._utils import normalize_text
from conversation.labeling.leakage import pool_issues
from conversation.labeling.models import ValidationResult
from conversation.labeling.storage import digest
from conversation.normalization import (
    CONSTRAINT_VALUE_ALIASES, CUISINE_ALIASES, PREFERENCE_ALIASES, SEMANTIC_ALIASES,
    canonical_values, normalize_update,
)
from conversation.reference_resolver import resolve_selector
from conversation.rule_parser import parse_by_rules_detailed
from conversation.state_manager import update_state


def validate_label(sample, payload, index, *, extra_errors=()):
    errors = list(extra_errors)
    warnings, risks = [], []
    overlap = index.overlap(sample)
    if overlap:
        errors.append(overlap)
    if sample.current_state and "relative_updates" in sample.current_state.context:
        errors.append("relative_event_in_input_context")
    ranks = [r.rank for r in sample.previous_results]
    if len(set(ranks)) != len(ranks):
        errors.append("duplicate_previous_result_rank")
    text = normalize_text(sample.message)
    rule = parse_by_rules_detailed(sample.message)
    if rule.requires_llm:
        risks.append("ambiguous_semantics")
        warnings.append("Rules leave unresolved text; human interpretation required")
    for category in ("references", "feedback", "correction", "absolute_relative", "allergy", "ambiguous"):
        if sample.category == category:
            risks.append(category)
    if re.search(r"dị ứng|allerg|an toàn", text):
        risks.append("allergy_safety")
    if re.search(r"thực ra|đổi sang|đổi thành|quá ồn|đắt quá|xa quá", text):
        risks.append("feedback_correction")
    if re.search(r"rẻ hơn|gần hơn", text) and re.search(r"\d+\s*(?:k\b|km|nghìn)", text):
        risks.append("absolute_relative_conflict")
    try:
        if payload is None:
            raise ValueError()
        update = PreferenceUpdate.model_validate(payload.model_dump() if isinstance(payload, PreferenceUpdate) else payload)
        state = update_state(sample.current_state, update,
            sample.current_state.session_id if sample.current_state else sample.sample_id)
    except (ValidationError, ValueError, TypeError, AttributeError):
        errors.append("invalid_preference_update_schema")
        return ValidationResult(passed=False, errors=sorted(set(errors)), warnings=warnings, risk_flags=sorted(set(risks)))

    hard = {**update.set_values.get("hard_constraints", {}), **update.add_hard_constraints}
    soft = {**update.set_values.get("soft_preferences", {}), **update.add_soft_preferences}
    if "parking" in hard or "parking" in soft:
        if not re.search(r"\bpark(?:ing)?\b|gửi xe|đậu xe|đỗ xe|bãi xe", text):
            errors.append("parking_without_explicit_evidence")
    normalized = normalize_update(update, sample.current_state)
    # Known aliases/duplicates must not leak into future training targets. Do
    # not silently rewrite a reviewed label or reject unknown cuisines/foods.
    for field, aliases in (("cuisine", CUISINE_ALIASES),
                           ("semantic_preferences", SEMANTIC_ALIASES),
                           ("negative_preferences", PREFERENCE_ALIASES)):
        values = update.set_values.get(field, [])
        if isinstance(values, list) and values != canonical_values(values, aliases):
            errors.append("noncanonical_" + field)
        if field != "cuisine":
            values = getattr(update, "add_" + field)
            if values != canonical_values(values, aliases):
                errors.append("noncanonical_" + field)
    for scope in ("hard_constraints", "soft_preferences"):
        for values in (update.set_values.get(scope, {}), getattr(update, "add_" + scope)):
            for key, aliases in CONSTRAINT_VALUE_ALIASES.items():
                if key in values and values[key] != canonical_values(values[key], aliases):
                    errors.append("noncanonical_" + key)
    # Reuse production removal-first precedence. Removals are allowed to resolve conflicts.
    effective_hard = {**normalized.set_values.get("hard_constraints", {}), **normalized.add_hard_constraints}
    for key in hard.keys() & soft.keys():
        if key in effective_hard:
            errors.append("hard_soft_conflict")
    for dimension, keys in (("budget", ("budget_min", "budget_max")),
                            ("distance", ("max_distance_km", "max_travel_time_min"))):
        absolute = {**effective_hard, **normalized.set_values.get("soft_preferences", {}),
                    **normalized.add_soft_preferences}
        if dimension in update.relative_updates and any(k in absolute for k in keys):
            errors.append("absolute_relative_conflict")
    if "distance" in update.relative_updates and not re.search(r"gần hơn|xa hơn", text):
        risks.append("unsupported_relative_distance")
        warnings.append("Distance direction lacks a recognized comparative; inspect manually")
        if re.search(r"đi bộ|gần gần|gần đây|không quá xa", text):
            errors.append("vague_near_is_not_relative")
    if "allergens_excluded" in soft:
        errors.append("allergy_in_soft_preferences")
    expected_allergens = rule.update.add_hard_constraints.get("allergens_excluded", [])
    exclusions = state.hard_constraints.get("allergens_excluded", [])
    if not isinstance(exclusions, list) or any(a not in exclusions for a in expected_allergens):
        errors.append("allergy_hard_exclusion_missing")
    if re.search(r"\bdị ứng\b", text) and not exclusions:
        errors.append("allergy_hard_exclusion_missing")
    # A different existing allergy must not hide a newly stated known allergen.
    for mention, aliases in (("tôm", {"shrimp", "shellfish", "tôm"}),
                             ("trứng", {"egg", "eggs", "trứng"}),
                             ("sữa", {"milk", "dairy", "sữa"})):
        if re.search(r"dị ứng\s+" + mention + r"\b", text):
            if not isinstance(exclusions, list) or not aliases.intersection(
                    normalize_text(str(v)) for v in exclusions):
                errors.append("allergy_hard_exclusion_missing")
    if "relative_updates" in update.set_values.get("context", {}) or "relative_updates" in state.context:
        errors.append("relative_event_in_context")
    if normalized.remove_preferences != update.remove_preferences:
        errors.append("noncanonical_removal_path")
    for path in update.remove_preferences:
        if "." in path:
            container, leaf = path.split(".", 1)
            if container not in {"hard_constraints", "soft_preferences", "context"} or not leaf or "." in leaf:
                errors.append("invalid_removal_path")
        elif path not in {"food", "cuisine"}:
            warnings.append("Legacy unqualified removal requires human interpretation")
    references = [*update.references, *update.set_values.get("reference_restaurants", [])]
    for ref in references:
        risks.append("references")
        if not isinstance(ref, dict):
            errors.append("invalid_reference")
            continue
        if ref.get("status") not in {"resolved", "unresolved"}:
            errors.append("invalid_reference_status")
        if ref.get("status") == "unresolved" and any(k in ref for k in ("restaurant_id", "menu_item_id", "similar_to")):
            errors.append("unresolved_reference_contains_id")
        if set(ref) - {"status", "rank", "restaurant_id", "menu_item_id", "restaurant_name", "dish_name", "mention", "sentiment", "similar_to"}:
            errors.append("unknown_reference_field")
        resolved = resolve_selector(ref, sample.previous_results)
        has_id = any(k in ref for k in ("restaurant_id", "menu_item_id"))
        if ref.get("status") == "resolved" or has_id:
            if resolved.get("status") != "resolved" or any(ref.get(k) != resolved.get(k) for k in ("restaurant_id", "menu_item_id") if k in ref):
                errors.append("invalid_reference_id_or_rank")
            if isinstance(ref.get("similar_to"), str) and ref["similar_to"] != resolved.get("restaurant_id"):
                errors.append("invalid_similar_to_id")
        elif ref.get("status") != "unresolved":
            errors.append("reference_not_resolved")
        else:
            warnings.append("Unresolved reference needs clarification; do not invent IDs")
    if update.set_values.get("reference_restaurants"):
        errors.append("references_must_use_resolver_field")
    return ValidationResult(passed=not errors, errors=sorted(set(errors)),
                            warnings=sorted(set(warnings)), risk_flags=sorted(set(risks)))


def validate_batch(samples, labels, index):
    by_id = {}
    for label in labels:
        if label.sample_id in by_id:
            raise ValueError("Duplicate teacher label IDs")
        by_id[label.sample_id] = label
    results = []
    for sample, errors in zip(samples, pool_issues(samples, index)):
        label = by_id.get(sample.sample_id)
        if label is None:
            errors.append("missing_teacher_label")
        elif label.sample_hash != digest(sample):
            errors.append("stale_teacher_label")
        if label and (label.error or label.status != "completed"):
            errors.append("provider_error")
        results.append(validate_label(sample, label.candidate if label else None, index, extra_errors=errors))
    return results
