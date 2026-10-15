"""Offline readiness check only. Never trains, loads weights or calls providers."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from common.schemas import PreferenceUpdate, PreviousResult, UserPreferenceState


def check_data(path):
    labels, fields, seen = Counter(), Counter(), Counter()
    errors = []
    total = 0
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        total += 1
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("sample must be an object")
            if row.get("schema_version") != "0.2":
                raise ValueError("schema_version must be 0.2; re-export legacy reviewed samples")
            if row.get("label_status") not in ("accepted", "corrected"):
                raise ValueError("only accepted/corrected labels allowed")
            data = row["input"]
            if not isinstance(data["message"], str):
                raise ValueError("message must be text")
            if data["old_state"] is not None:
                UserPreferenceState.model_validate(data["old_state"])
            if not isinstance(data["previous_results"], list):
                raise ValueError("previous_results must be an array")
            for item in data["previous_results"]:
                PreviousResult.model_validate(item)
            target = PreferenceUpdate.model_validate(row["target"]).model_dump(mode="json")
            labels[row["label_status"]] += 1
            fields.update(key for key, value in target.items() if value)
            seen[json.dumps({"input": data, "target": target}, sort_keys=True, ensure_ascii=False)] += 1
        except ValidationError:
            # Pydantic messages embed input values; never echo dataset content.
            errors.append({"line": line_number, "error": "invalid input or target schema"})
        except (ValueError, KeyError, TypeError) as exc:
            errors.append({"line": line_number, "error": str(exc)})
    if not total:
        errors.append({"line": 0, "error": "empty dataset"})
    return {"total": total, "valid": sum(labels.values()), "labels": dict(labels),
            "duplicate_count": sum(count - 1 for count in seen.values()),
            "field_frequencies": dict(fields), "errors": errors, "training_enabled": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-data", required=True, type=Path)
    args = parser.parse_args(argv)
    result = check_data(args.check_data)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(bool(result["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
