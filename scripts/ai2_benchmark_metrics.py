"""Exact/domain and fact-level diagnostics; no schema duplication or label repair."""
import json
import math
from collections import defaultdict

from common.schemas import PreferenceUpdate, UserPreferenceState
from conversation.normalization import normalize_update
from conversation.state_manager import update_state


def facts(value, path=""):
    """Empty scaffolding contributes no true positives; scalar lists are sets.

    Exact metrics separately retain list order/duplicate sensitivity. Reference
    dictionaries retain index paths to detect mismatched/multiple selectors.
    """
    result = set()
    if isinstance(value, dict):
        for key, item in value.items():
            result |= facts(item, f"{path}.{key}".strip("."))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            result |= facts(item, f"{path}[{i}]" if isinstance(item, dict) else path)
    elif value is not None:
        result.add((path, json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)))
    return result


def prf(expected, actual):
    gold, predicted = facts(expected), facts(actual or {})
    tp, fp, fn = len(gold & predicted), len(predicted - gold), len(gold - predicted)
    return counts_prf(tp, fp, fn)


def counts_prf(tp, fp, fn):
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return dict(tp=tp, fp=fp, fn=fn, precision=precision, recall=recall, f1=f1)


def exact_metric(expected, actual):
    return expected == actual if actual is not None else False


def score(case, delta, actual_state=None, *, raw=False):
    expectation = case.get("expected_raw_update" if raw else "expected_update")
    if expectation is None:
        return None
    target = PreferenceUpdate.model_validate(expectation).model_dump(mode="json")
    actual = delta.model_dump(mode="json") if isinstance(delta, PreferenceUpdate) else delta
    metric = {"delta_exact": exact_metric(target, actual), "field_prf": prf(target, actual)}
    for name in ("references", "relative_updates", "context_updates"):
        metric[name + "_exact"] = actual is not None and actual.get(name, {}) == target[name]
    metric["reference_fields"] = {
        field: prf({"references": [{field: r[field]} for r in target["references"] if field in r]},
                   {"references": [{field: r[field]} for r in (actual or {}).get("references", [])
                                   if isinstance(r, dict) and field in r]})
        for field in ("rank", "mention", "restaurant_id", "menu_item_id")}
    extra = facts(actual or {}) - facts(target)
    metric["unexpected_facts"] = sorted([{"path": p, "value": json.loads(v)} for p, v in extra], key=lambda x: (x["path"], str(x["value"])))
    gold_state = UserPreferenceState.model_validate(case["expected_state"]).model_dump(mode="json")
    if actual_state is not None:
        actual_state = actual_state.model_dump(mode="json") if isinstance(actual_state, UserPreferenceState) else actual_state
        metric["state_exact"] = gold_state == actual_state
        # Identity fields are constant fixtures, not extraction successes.
        metric["state_prf"] = prf({k: v for k, v in gold_state.items() if k not in ("session_id", "user_id")},
                                  {k: v for k, v in actual_state.items() if k not in ("session_id", "user_id")})
        gold_hard, hard = gold_state["hard_constraints"], actual_state["hard_constraints"]
        gold_allergy, allergy = set(gold_hard.get("allergens_excluded", [])), set(hard.get("allergens_excluded", []))
        metric["allergy_fp"] = sorted(allergy - gold_allergy)
        metric["allergy_fn"] = sorted(gold_allergy - allergy)
        metric["hard_prf"] = prf(gold_hard, hard)
        metric["travel_time_exact"] = gold_hard.get("max_travel_time_min") == hard.get("max_travel_time_min")
    else:
        metric["state_exact"] = None
    return metric


def raw_stages(case, delta):
    if delta is None:
        return {"raw": score(case, None, raw=True), "canonical": score(case, None, raw=True),
                "projected_state": None, "projection_error": "invalid_delta"}
    canonical = normalize_update(delta)
    projected = None
    error = None
    try:
        # A deliberately unguarded model-only projection: applies canonical
        # State Manager semantics, without Rule merge, reference resolution or
        # parser evidence validation. Report this distinction explicitly.
        initial = UserPreferenceState.model_validate(case["current_state"]) if case.get("current_state") else None
        projected = update_state(initial, delta, "adapter-regression")
    except (ValueError, TypeError):
        error = "invalid_state_projection"
    return {"raw": score(case, delta, projected, raw=True),
            "canonical": score(case, canonical, projected, raw=True),
            "projected_state": projected.model_dump(mode="json") if projected else None, "projection_error": error}


def latency(values):
    values = sorted(v for v in values if v is not None)
    return {"n": len(values), "p50_ms": values[math.ceil(.5 * len(values)) - 1] if values else None,
            "p95_ms": values[math.ceil(.95 * len(values)) - 1] if len(values) >= 20 else None,
            "p95_note": "nearest-rank empirical estimate; small diagnostic sample" if len(values) >= 20 else "not reported: fewer than 20 warm measurements"}


def summary(records):
    result = {}
    for stage in ("rule", "raw", "canonical", "effective"):
        scored = [r["scores"][stage] for r in records if r["scores"].get(stage) is not None]
        result[stage] = {"scored": len(scored), "delta_exact": sum(s["delta_exact"] for s in scored),
                         "state_exact": sum(s.get("state_exact") is True for s in scored),
                         "state_scored": sum(s.get("state_exact") is not None for s in scored),
                         "allergy_fp": sum(len(s.get("allergy_fp", [])) for s in scored),
                         "allergy_fn": sum(len(s.get("allergy_fn", [])) for s in scored)}
        for field in ("field_prf", "state_prf", "hard_prf"):
            counts = [s[field] for s in scored if field in s]
            result[stage][field] = counts_prf(*(sum(c[k] for c in counts) for k in ("tp", "fp", "fn"))) if counts else None
        result[stage]["category"] = {}
        for category in sorted({r["category"] for r in records}):
            subset = [r["scores"][stage] for r in records if r["category"] == category and r["scores"].get(stage) is not None]
            passed = sum(s["delta_exact"] and s.get("state_exact") is not False for s in subset)
            result[stage]["category"][category] = {"scored": len(subset), "pass": passed, "fail": len(subset) - passed}
    actual = [r for r in records if r.get("slm_result") is not None]
    result["raw_json_valid"] = sum(r.get("json_valid") is True for r in actual)
    result["raw_schema_valid"] = sum(r.get("schema_valid") is True for r in actual)
    result["raw_inferred"] = len(actual)
    result["invalid_outputs"] = len(actual) - result["raw_schema_valid"]
    result["warm_generation"] = latency([r.get("generation_ms") for r in records[1:]])
    result["first_generation_ms"] = records[0].get("generation_ms") if records else None
    result["production_slm_calls"] = sum(r.get("effective", {}).get("metadata", {}).get("slm_called", False) for r in records)
    result["production_slm_fallbacks"] = sum(r.get("effective", {}).get("metadata", {}).get("slm_fallback", False) for r in records)
    result["requires_external_fallback"] = sum(r.get("effective", {}).get("metadata", {}).get("requires_llm", False)
        and r.get("effective", {}).get("metadata", {}).get("parser_used") == "rule_fallback" for r in records)
    result["clarification_required"] = sum(r.get("effective", {}).get("metadata", {}).get("clarification_required", False) for r in records)
    result["human_review_unscored"] = sum(r["scores"]["rule"] is None for r in records)
    return result
