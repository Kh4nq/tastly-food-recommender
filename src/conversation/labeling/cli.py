"""Shared entry points for local labeling scripts, with safe offline defaults."""
import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from conversation.labeling.generation import generate_samples
from conversation.labeling.leakage import LeakageIndex, filter_pool
from conversation.labeling.models import PromptSample, ReviewItem, ReviewRecord, TeacherLabel
from conversation.labeling.review import build_queue, counts, export_records
from conversation.labeling.storage import DEFAULT_DIRECTORY, guard_output, read_rows, write_rows
from conversation.labeling.teacher import label_samples
from conversation.labeling.validation import validate_batch


def load_models(path, model):
    return [model.model_validate(row) for row in read_rows(path)]


def save_exclusions(path, exclusions):
    # A deterministic report contains hashes and IDs, never copied benchmark text.
    write_rows(Path(str(path) + ".excluded.jsonl"), exclusions, replace=True)


def generate_pool(args, index):
    independent = generate_samples(args.count, args.seed, multi_turn=not args.single_turn,
                                   with_results=not args.no_previous_results)
    samples, excluded = filter_pool(independent, index)
    write_rows(args.output, samples)
    save_exclusions(args.output, excluded)
    return samples, excluded


def main(command, argv=None):
    parser = argparse.ArgumentParser(description="AI2 candidate labeling; explicit human review required")
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    if command in {"generate", "prepare"}:
        parser.add_argument("--count", type=int, default=200)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--single-turn", action="store_true")
        parser.add_argument("--no-previous-results", action="store_true")
    if command in {"teacher", "prepare"}:
        parser.add_argument("--provider", choices=["rule", "gemini"], default="rule")
        parser.add_argument("--dry-run", "--offline", action="store_true", help="Force rule provider; never load credentials or call APIs")
    if command != "prepare":
        parser.add_argument("--output", type=Path)
    if command in {"teacher", "validate", "queue"}:
        parser.add_argument("--pool", type=Path)
    if command in {"validate", "queue"}:
        parser.add_argument("--labels", type=Path)
    if command == "export":
        parser.add_argument("--queue", type=Path)
        parser.add_argument("--reviewed", type=Path)
        parser.add_argument("--only-unresolved", action="store_true")
    if command == "queue":
        parser.add_argument("--stats", action="store_true", help="Inspect existing review queue counts")
    args = parser.parse_args(argv)
    directory = args.directory
    pool_path = getattr(args, "pool", None) or directory / "prompt_pool.jsonl"
    labels_path = getattr(args, "labels", None) or directory / "teacher_labels.jsonl"
    queue_path = getattr(args, "queue", None) or directory / "review_queue.jsonl"
    review_path = getattr(args, "reviewed", None) or directory / "reviewed.jsonl"
    defaults = {"generate": pool_path, "teacher": labels_path, "validate": directory / "validation.jsonl",
                "queue": queue_path, "export": directory / "training_v02.jsonl"}
    if command != "prepare":
        args.output = args.output or defaults[command]
    try:
        index = LeakageIndex.from_benchmark()
        if command == "generate":
            samples, excluded = generate_pool(args, index)
            report = {"generated": len(samples), "excluded": len(excluded)}
        elif command == "teacher":
            guard_output(args.output, pool_path)
            labels, excluded = label_samples(load_models(pool_path, PromptSample), args.output, index,
                                            provider="rule" if args.dry_run else args.provider)
            save_exclusions(args.output, excluded)
            report = {"labels": len(labels), "excluded": len(excluded), "errors": sum(bool(l.error) for l in labels)}
        elif command == "validate":
            guard_output(args.output, pool_path, labels_path)
            samples = load_models(pool_path, PromptSample)
            results = validate_batch(samples, load_models(labels_path, TeacherLabel), index)
            write_rows(args.output, [{"sample_id": s.sample_id, **v.model_dump(mode="json")}
                                     for s, v in zip(samples, results)], replace=True)
            report = {"total": len(results), "passed": sum(v.passed for v in results)}
            print(json.dumps(report))
            return int(any(not v.passed for v in results))
        elif command == "queue":
            if args.stats:
                report = counts(load_models(args.output, ReviewItem))
            else:
                guard_output(args.output, pool_path, labels_path)
                samples, excluded = filter_pool(load_models(pool_path, PromptSample), index)
                queue = build_queue(samples, load_models(labels_path, TeacherLabel), index)
                write_rows(args.output, queue)
                save_exclusions(args.output, excluded)
                report = counts(queue)
        elif command == "export":
            guard_output(args.output, queue_path, review_path)
            queue = load_models(queue_path, ReviewItem)
            reviews = load_models(review_path, ReviewRecord) if review_path.exists() else []
            training, excluded = export_records(queue, reviews, index, only_unresolved=args.only_unresolved)
            write_rows(args.output, training)
            save_exclusions(args.output, excluded)
            report = {"exported": len(training), "excluded": len(excluded)}
        elif command == "prepare":
            args.output = pool_path
            samples, excluded = generate_pool(args, index)
            labels, teacher_excluded = label_samples(samples, labels_path, index,
                provider="rule" if args.dry_run else args.provider)
            save_exclusions(labels_path, teacher_excluded)
            validations = validate_batch(samples, labels, index)
            write_rows(directory / "validation.jsonl", [{"sample_id": s.sample_id, **v.model_dump(mode="json")}
                for s, v in zip(samples, validations)], replace=True)
            queue = build_queue(samples, labels, index)
            write_rows(queue_path, queue)
            report = {**counts(queue), "excluded": len(excluded), "stopped_before_human_review": True,
                      "provider": "rule" if args.dry_run else args.provider}
        else:
            raise ValueError("Unknown command")
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    except (ValidationError, ValueError, OSError):
        # Never emit exception text or Pydantic input excerpts (which may contain secrets).
        print(json.dumps({"error": "Artifact/configuration error. Check paths, schemas, writer locks and resume identity; existing artifacts are preserved."}))
        return 2
