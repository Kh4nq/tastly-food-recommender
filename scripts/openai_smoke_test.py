"""Explicit, bounded OpenAI smoke run; importing this module never calls APIs."""
import argparse
import sys

from ai2_tools import ConversationConfig, dump, load_env, make_provider, run_case
from conversation.providers import ProviderError

CASES = [
    {"id": "openai_smoke_1", "category": "combined",
     "message": "Muốn ăn cơm tấm dưới 50k, gần gần thôi",
     "current_state": {}, "previous_results": [],
     "expected": {"food": ["cơm tấm"], "hard_constraints": {"budget_max": 50000},
                  "soft_preferences": {"distance": "near"}}},
    {"id": "openai_smoke_2", "category": "hard",
     "message": "Muốn ăn ramen dưới 150k, bắt buộc có chỗ đậu xe.",
     "current_state": {}, "previous_results": [],
     "expected": {"food": ["ramen"], "hard_constraints": {"budget_max": 150000, "parking": True}}},
]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=int, choices=range(1, len(CASES) + 1), default=1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    load_env()
    config = ConversationConfig.from_env()
    provider = None
    try:
        if not args.dry_run:
            print("Explicit smoke run: may consume OpenAI API quota.")
            provider = make_provider("openai", config)
        record = run_case(CASES[args.case - 1], provider, config, args.dry_run, provider_name="openai")
        print(dump(record, config))
        return int(record["status"] == "FAIL")
    except ProviderError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        if provider is not None:
            provider.close()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
