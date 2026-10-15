"""Compare immutable diagnostics before/after guards; no benchmark relabeling."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from scripts.benchmark_ai2_freeze import DEFAULT_SUITE, sha256


def compare_guard_replay(before, after):
    if before["suite_sha256"] != after["suite_sha256"]:
        raise ValueError("Frozen diagnostic suite differs")
    if after.get("mode") != "replay":
        raise ValueError("Guard isolation requires a replay, not fresh generation")
    old = {c["id"]: c for c in before["cases"]}
    if set(old) != {c["id"] for c in after["cases"]}:
        raise ValueError("Incomplete paired replay")
    source_changes = [p for p in before["source_checksums"]
                      if before["source_checksums"][p] != after["source_checksums"].get(p)]
    if any(not p.startswith("src/conversation/") for p in source_changes):
        raise ValueError("Guard comparison found changes outside AI2")
    changes = []
    for new in after["cases"]:
        prior = old[new["id"]]
        if prior["raw_response"] != new["raw_response"] or prior["slm_result"] != new["slm_result"]:
            raise ValueError("Replay altered a frozen model output")
        if prior["label_status"] != new["label_status"]:
            raise ValueError("Case label status changed")
        changes.append({"id": new["id"], "label_status": new["label_status"],
            "raw_response_identical": True, "current_slm_input_changed": prior["input"] != new["input"],
            "before": prior["effective"], "after": new["effective"],
            "before_score": prior["scores"]["effective"], "after_score": new["scores"]["effective"]})
    return {"interpretation": "Same historical raw outputs; changed current rules/guards. Not fresh model accuracy or latency.",
            "source_changes": source_changes, "before_summary": before["summary"],
            "after_summary": after["summary"], "cases": changes}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before-dir", type=Path, default=Path("logs/ai2-freeze-20261015"))
    parser.add_argument("--after-dir", type=Path, default=Path("logs/ai2-safety-patch-20261015"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Choose a new report filename; frozen reports are never overwritten")
    report = {"suite_sha256": sha256(DEFAULT_SUITE), "evaluation_kind": "diagnostic regressions",
              "independent_gold_count": 0, "adapters": {}}
    for adapter in ("v3", "v4"):
        before_path = args.before_dir / (adapter + ".json")
        after_path = args.after_dir / (adapter + "-guard-replay.json")
        before = json.loads(before_path.read_text(encoding="utf-8"))
        after = json.loads(after_path.read_text(encoding="utf-8"))
        if before["suite_sha256"] != report["suite_sha256"]:
            parser.error("Frozen suite file was modified")
        comparison = compare_guard_replay(before, after)
        comparison["report_checksums"] = {str(p): sha256(p) for p in (before_path, after_path)}
        report["adapters"][adapter] = comparison
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Guard-only paired report saved; original outputs and diagnostic labels preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
