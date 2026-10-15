"""AI 2 benchmark harness. Default mock performs no semantic inference or API calls."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from ai2_tools import (ROOT, ConversationConfig, dump, load_env, make_provider,
                       request_for, run_case, summarize)
from conversation.providers import ProviderError


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("count must be positive")
    return number


def load_dataset(path):
    samples = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            sample = json.loads(line)
            for key in ("id", "category", "message", "current_state", "previous_results", "expected"):
                if key not in sample:
                    raise ValueError("Missing dataset field")
            if not isinstance(sample["category"], str) or not sample["category"].strip():
                raise ValueError("Invalid category")
            request_for(sample)  # Validate the full dataset before paid requests.
            samples.append(sample)
    if not samples or len({s["id"] for s in samples}) != len(samples):
        raise ValueError("Empty dataset or duplicate IDs")
    return samples


def select_samples(samples, categories=None, one_per_category=False, per_category=None, limit=None):
    """Filter, cap each category in dataset order, then apply the global limit."""
    if one_per_category and per_category is not None:
        raise ValueError("use either --one-per-category or --per-category, not both.")
    valid = list(dict.fromkeys(sample["category"] for sample in samples))
    unknown = [name for name in categories or [] if name not in valid]
    if unknown:
        raise ValueError(f"Unknown categories: {', '.join(unknown)}. Valid categories: {', '.join(valid)}")
    selected = [sample for sample in samples if categories is None or sample["category"] in categories]
    cap = 1 if one_per_category else per_category
    if cap is not None:
        groups = {}
        for sample in selected:
            group = groups.setdefault(sample["category"], [])
            if len(group) < cap:
                group.append(sample)
        selected = [sample for group in groups.values() for sample in group]
    return selected[:limit]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["mock", "gemini", "openai"], default="mock")
    parser.add_argument("--limit", type=positive_int)
    parser.add_argument("--categories", nargs="+", help="Only include these dataset categories")
    parser.add_argument("--one-per-category", action="store_true", help="Select the first sample of each category")
    parser.add_argument("--per-category", type=positive_int, help="Select at most N samples per category")
    parser.add_argument("--list-categories", action="store_true", help="List dataset category counts without a provider")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dataset", type=Path, default=ROOT / "benchmarks/ai2_vietnamese_prompts.jsonl")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "benchmarks/results")
    args = parser.parse_args(argv)
    if args.one_per_category and args.per_category is not None:
        parser.error("use either --one-per-category or --per-category, not both.")
    if (args.provider in ("gemini", "openai") and not args.list_categories
            and args.limit is None and not args.one_per_category and args.per_category is None):
        parser.error(f"--provider {args.provider} requires an explicit --limit, --one-per-category or --per-category, including dry-run")
    provider = None
    try:
        samples = load_dataset(args.dataset)
        if args.list_categories:
            counts = Counter(sample["category"] for sample in samples)
            for category, count in counts.items():
                print(f"{category}: {count}")
            print(f"\nTOTAL:\n{len(counts)} categories\n{len(samples)} samples")
            return 0
        try:
            samples = select_samples(samples, args.categories, args.one_per_category, args.per_category, args.limit)
        except ValueError as exc:
            parser.error(str(exc))
        category_names = list(dict.fromkeys(sample["category"] for sample in samples))
        load_env()
        config = ConversationConfig.from_env()
        args.output_dir.mkdir(parents=True, exist_ok=True)
        if args.provider in ("gemini", "openai") and not args.dry_run:
            label = {"gemini": "Gemini", "openai": "OpenAI"}[args.provider]
            print(f"You are about to process {len(samples)} benchmark samples across {len(category_names)} categories. {label} calls may consume quota.")
        provider = None if args.dry_run else make_provider(args.provider, config)
        records = [run_case(sample, provider, config, args.dry_run, provider_name=args.provider) for sample in samples]
        report = {"provider": args.provider, "model": getattr(config, args.provider + "_model", None),
                  "number_prompts": len(samples), "dry_run": args.dry_run,
                  "selection": {"categories": category_names, "one_per_category": args.one_per_category,
                                "per_category": args.per_category, "limit": args.limit},
                  "mock_behavior": "empty inference; not a model-quality benchmark" if args.provider == "mock" else None,
                  "summary": summarize(records), "cases": records}
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        path = args.output_dir / f"ai2_{args.provider}_{timestamp}.json"
        path.write_text(dump(report, config) + "\n", encoding="utf-8")
        print(dump(report["summary"], config))
        print(f"Result: {path}")
        return 0
    except ProviderError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (ValueError, OSError):
        print("Invalid dataset or inaccessible input/output path; no exception details logged.", file=sys.stderr)
        return 2
    finally:
        if args.provider in ("gemini", "openai") and provider is not None:
            provider.close()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
