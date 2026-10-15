"""Opt-in real Gemini smoke test. Never collected by pytest."""
import argparse
import sys

from ai2_tools import ConversationConfig, dump, load_env, make_provider, run_case
from conversation.providers import ProviderError

RESULTS = [{"rank": 1, "restaurant_id": "R001", "restaurant_name": "A"},
           {"rank": 2, "restaurant_id": "R002", "restaurant_name": "B"}]
CASES = [
    {"message": "Tìm ramen dưới 150k trong vòng 2km", "category": "combined",
     "expected": {"food": ["ramen"], "hard_constraints": {"budget_max": 150000, "max_distance_km": 2},
                  "metadata": {"llm_called": False}}},
    {"message": "Muốn quán đẹp để đi date nhưng đừng quá ồn.", "category": "semantic",
     "review": "Beautiful ambience; suitable for a date; not too noisy. Accept equivalent meanings."},
    {"message": "Xa quá, tìm gần hơn đi. Đắt thêm một chút cũng được.", "category": "relative",
     "current_state": {"hard_constraints": {"budget_max": 150000, "max_distance_km": 3}},
     "expected": {"hard_constraints": {"budget_max": 150000, "max_distance_km": 3},
                  "relative_updates": {"distance": "decrease", "budget": "increase"}},
     "absent": ["update.add_hard_constraints.budget_max", "update.add_hard_constraints.max_distance_km"]},
    {"message": "Không cần quán đẹp nữa nhưng vẫn muốn yên tĩnh.", "category": "removal",
     "current_state": {"semantic_preferences": ["beautiful ambience", "quiet"]},
     "expected": {"semantic_preferences": ["quiet"], "update": {"remove_preferences": ["beautiful ambience"]}},
     "review": "Verify beautiful ambience is removed and quiet is retained; equivalent labels accepted."},
    {"message": "Muốn ăn ramen dưới 150k, bắt buộc có chỗ đậu xe.", "category": "hard",
     "expected": {"food": ["ramen"], "hard_constraints": {"budget_max": 150000, "parking": True}}},
    {"message": "Có chỗ đậu xe thì tốt nhưng không bắt buộc.", "category": "soft_hard",
     "absent": ["hard_constraints.parking"], "review": "Parking should be optional, not mandatory."},
    {"message": "Cái thứ hai khá ổn nhưng hơi xa, tìm quán giống nó mà gần hơn.", "category": "feedback",
     "previous_results": RESULTS,
     "expected": {"relative_updates": {"distance": "decrease"}, "reference_restaurants": [
         {"restaurant_id": "R002", "similar_to": "R002", "sentiment": "positive"}]}},
    {"message": "Không muốn ăn đồ cay, tìm món Nhật nhẹ nhàng một chút.", "category": "negative",
     "expected": {"reference_restaurants": []},
     "review": "Negative spicy; Japanese cuisine or equivalent meaning; no invented restaurant."},
]
for number, case in enumerate(CASES, 1):
    case.update(id=f"smoke_{number}")
    case.setdefault("expected", {})
    case.setdefault("current_state", {})
    case.setdefault("previous_results", [])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=int, choices=range(1, 9))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    load_env()
    config = ConversationConfig.from_env()
    cases = [CASES[args.case - 1]] if args.case else CASES
    provider = None
    try:
        if not args.dry_run:
            provider = make_provider("gemini", config)
            print(f"Explicit smoke run: up to {len(cases)} Gemini API calls; consumes quota.")
        failed = False
        for index, sample in enumerate(cases):
            record = run_case(sample, provider, config, args.dry_run)
            result = record["result"]
            print("-" * 50)
            print(f"CASE {sample['id'].split('_')[-1]}\nMESSAGE:\n{record['message']}")
            print("RULE RESULT:\n" + dump(result["rule_result"], config))
            print("GEMINI CALLED:\n" + str(record["gemini_called"]).lower())
            print("PARSER USED:\n" + result["metadata"]["parser_used"])
            print("PREFERENCE UPDATE:\n" + dump(result["preference_update"], config))
            print("FINAL STATE:\n" + dump(result["state"], config))
            meta = result["metadata"]
            print(f"LATENCY:\nrule_ms = {meta['rule_parse_ms']:.3f}\nllm_ms = {meta['llm_ms']:.3f}\ntotal_ms = {meta['total_ms']:.3f}")
            print("METADATA:\n" + dump(meta, config))
            if args.dry_run:
                print("WOULD CALL GEMINI: " + str(record["would_call_gemini"]))
                print("PLANNED REQUEST:\n" + dump(record["planned_request"], config))
            print("CHECKS:\n" + dump(record["checks"], config))
            print("STATUS:\n" + record["status"])
            if record["review"]:
                print("REVIEW: " + record["review"])
            failed |= record["status"] == "FAIL"
        return int(failed)
    except ProviderError as exc:
        print(str(exc), file=sys.stderr)  # Only bounded adapter configuration messages.
        return 2
    finally:
        if provider is not None:
            provider.close()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
