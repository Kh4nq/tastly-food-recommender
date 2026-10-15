"""Deterministic rule-only diagnostics; no benchmark, provider, or model access.

The authored expectations describe semantics, not a target call-reduction rate.
Print summary JSON by default, or every diagnostic row with --details. Redirect
reports to an ignored directory (for example .pytest_cache), never to fixtures.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from common.schemas import PreferenceUpdate
from conversation.normalization import normalize_update
from conversation.rule_parser import parse_by_rules_detailed


def audit_pool(seed=20261001):
    """240 unique prompts: 40 semantic cases, six surface forms each."""
    cases = [
        ("budget", "ngân sách tối đa {b} nghìn", {"add_hard_constraints": {"budget_max": "B"}}),
        ("price", "giá dưới {b}k", {"add_hard_constraints": {"budget_max": "B"}}),
        ("budget", "budget {b}k", {"add_hard_constraints": {"budget_max": "B"}}),
        ("distance", "khoảng cách trong vòng {d}km", {"add_hard_constraints": {"max_distance_km": "D"}}),
        ("distance", "khoảng cách tối đa {d}km", {"add_hard_constraints": {"max_distance_km": "D"}}),
        ("distance", "trong {d}km", {"add_hard_constraints": {"max_distance_km": "D"}}),
        ("travel_time", "đi bộ không quá 15 phút", {"context_updates": {"transport_mode": "walking"}, "add_hard_constraints": {"max_travel_time_min": 15}}),
        ("food", "món phở", {"set_values": {"food": ["phở"]}}),
        ("food", "món ăn sushi", {"set_values": {"food": ["sushi"]}}),
        *[("cuisine", phrase, {"set_values": {"cuisine": [value]}}) for phrase, value in (
            ("món Hàn", "korean"), ("đồ Nhật", "japanese"), ("món Việt", "vietnamese"),
            ("đồ Trung Quốc", "chinese"), ("món Thái", "thai"), ("đồ Ý", "italian"), ("món Tây", "western"))],
        ("parking_soft", "có parking thì tốt", {"add_soft_preferences": {"parking": True}}),
        ("parking_hard", "bắt buộc có chỗ gửi xe", {"add_hard_constraints": {"parking": True}}),
        ("negative", "không thích cay", {"add_negative_preferences": ["spicy"]}),
        ("allergy", "dị ứng lạc", {"add_hard_constraints": {"allergens_excluded": ["peanut"]}}),
        ("transport", "đi xe máy", {"context_updates": {"transport_mode": "motorbike"}}),
        ("occasion", "đi date", {"context_updates": {"occasion": "date"}}),
        ("companions", "ăn với gia đình", {"context_updates": {"companions": ["family"]}}),
        ("party_size", "nhóm 4 người", {"context_updates": {"party_size": 4}}),
        ("meal_time", "bữa trưa", {"context_updates": {"meal_time": "lunch"}}),
        ("relative", "rẻ hơn", {"relative_updates": {"budget": "decrease"}}),
        ("absolute_relative", "rẻ hơn, dưới {b}k", {"add_hard_constraints": {"budget_max": "B"}}),
        ("removal", "bỏ giới hạn ngân sách", {"remove_preferences": ["hard_constraints.budget_max"]}),
        ("semantic", "quán yên tĩnh", {"add_semantic_preferences": ["quiet"]}),
        # Deliberately unresolved controls. None may become rule-resolved just
        # because a budget, dish, or context was extracted elsewhere.
        ("meaningful_residual", "tối đa {b}k nhưng muốn quán thật yên tĩnh", None),
        ("unknown_food", "mì quảng", None),
        ("rating", "phở, đánh giá ít nhất 4 sao", None),
        ("soft_numeric", "giá dưới {b}k thì tốt", None),
        ("condition", "phở nếu có parking", None),
        ("negation", "không muốn món Hàn", None),
        ("correction", "ramen chuyển qua sushi", None),
        ("reference", "quán thứ hai", None),
        ("unmatched_domain", "dưới {b}k, khoảng cách", None),
        ("unknown_modifier", "trong {d}km, có phòng riêng", None),
        ("ambiguous_cuisine_word", "phở theo ý mình", None),
    ]
    wrappers = ("{}", "hôm nay {} nhé", "cho mình {} được không", "giúp mình tìm {}", "tôi muốn {} nha", "mình muốn {} thôi")
    rng = random.Random(seed)
    rows = []
    for category, template, expected in cases:
        for wrapper in wrappers:
            budget, distance = rng.choice((65, 85, 120, 175)), rng.choice((1, 2, 3, 5))
            payload = json.loads(json.dumps(expected).replace('"B"', str(budget * 1000)).replace('"D"', str(distance))) if expected is not None else None
            rows.append({"category": category, "message": wrapper.format(template.format(b=budget, d=distance)),
                         "expected": payload, "expected_requires_llm": expected is None})
    return rows


def normalization_probes():
    # Independent expected vocabulary; do not derive the oracle from production aliases.
    for canonical, aliases in (
        ("korean", ("Hàn", "đồ Hàn", "Korean")),
        ("japanese", ("Nhật", "món Nhật", "Japanese")),
        ("vietnamese", ("Việt", "đồ Việt", "Vietnamese")),
        ("chinese", ("Trung Quốc", "món Hoa", "Chinese")),
        ("thai", ("Thái", "đồ Thái", "Thai")),
        ("italian", ("Ý", "món Ý", "Italian")),
        ("western", ("Tây", "đồ Tây", "Western")),
    ):
        for alias in aliases:
            yield {"set_values": {"cuisine": [alias, canonical]}}, {"set_values": {"cuisine": [canonical]}}
    for key, alias, canonical in (
        ("transport_mode", "xe máy", "motorbike"), ("transport_mode", "đi bộ", "walking"),
        ("occasion", "đi date", "date"), ("occasion", "gia đình", "family"),
        ("meal_time", "trưa nay", "lunch"), ("companions", ["gia đình", "family"], ["family"]),
    ):
        yield {"context_updates": {key: alias}}, {"context_updates": {key: canonical}}
    yield {"add_semantic_preferences": ["yên tĩnh", "quiet"]}, {"add_semantic_preferences": ["quiet"]}
    yield {"add_negative_preferences": ["đồ cay", "spicy"]}, {"add_negative_preferences": ["spicy"]}
    yield {"set_values": {"food": ["mì quảng"]}}, {"set_values": {"food": ["mì quảng"]}}


def run_audit(seed=20261001):
    pool = audit_pool(seed)
    rows = []
    for case in pool:
        rule = parse_by_rules_detailed(case["message"])
        flags = []
        expected = PreferenceUpdate.model_validate(case["expected"]) if case["expected"] is not None else None
        exact = expected is not None and rule.update == expected
        if exact and rule.requires_llm:
            flags.append("redundant_llm")
        if not rule.requires_llm and (case["expected_requires_llm"] or not exact):
            flags.append("false_resolved")
        if expected is not None and not exact:
            flags.append("semantic_mismatch")
        hard, soft = rule.update.add_hard_constraints, rule.update.add_soft_preferences
        if hard.keys() & soft.keys() or any(
            dim in rule.update.relative_updates and any(k in hard or k in soft for k in keys)
            for dim, keys in (("budget", ("budget_min", "budget_max")), ("distance", ("max_distance_km", "max_travel_time_min")))
        ):
            flags.append("conflicting_updates")
        rows.append({**case, "recognized_spans": rule.matched_spans, "unresolved_text": rule.unresolved_text,
                     "requires_llm": rule.requires_llm, "update": rule.update.model_dump(mode="json"), "flags": flags})
    probes = []
    for payload, expected in normalization_probes():
        try:
            actual = normalize_update(PreferenceUpdate.model_validate(payload))
            consistent = actual == PreferenceUpdate.model_validate(expected)
        except ValueError:
            consistent = False
        probes.append({"input": payload, "expected": expected, "consistent": consistent})
    counts = Counter(flag for row in rows for flag in row["flags"])
    summary = {"seed": seed, "pool_sha256": hashlib.sha256(json.dumps(pool, sort_keys=True).encode()).hexdigest(),
               "total": len(rows), "rule_resolved": sum(not r["requires_llm"] for r in rows),
               "requires_llm": sum(r["requires_llm"] for r in rows),
               **{name: counts[name] for name in ("redundant_llm", "false_resolved", "semantic_mismatch", "conflicting_updates")},
               "normalization_probes": len(probes), "canonicalization_inconsistencies": sum(not p["consistent"] for p in probes)}
    return {"summary": summary, "rows": rows, "normalization": probes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261001)
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    report = run_audit(args.seed)
    print(json.dumps(report if args.details else report["summary"], ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
