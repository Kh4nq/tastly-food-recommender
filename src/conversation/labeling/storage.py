"""Atomic local artifacts, exclusive writers, and credential-safe persistence."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path

from conversation.interactive.dataset_logger import DatasetLogger

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DIRECTORY = ROOT / "data/ai2_labeling"
BENCHMARK = ROOT / "benchmarks/ai2_vietnamese_prompts.jsonl"


def digest(value) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    allow_nan=False).encode("utf-8")).hexdigest()


def read_rows(path: Path) -> list[dict]:
    rows = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError(f"Invalid JSON object at line {number}") from None
        rows.append(row)
    return rows


def guard_output(path: Path, *inputs: Path) -> None:
    resolved = Path(path).resolve()
    if resolved == BENCHMARK.resolve() or BENCHMARK.parent.resolve() in resolved.parents:
        raise ValueError("Writing benchmark artifacts is forbidden")
    if resolved in {Path(p).resolve() for p in inputs}:
        raise ValueError("Output must differ from input artifacts")


def write_rows(path: Path, rows, *, replace: bool = False) -> None:
    path = Path(path)
    guard_output(path)
    payload = [r.model_dump(mode="json") if hasattr(r, "model_dump") else r for r in rows]
    logger = DatasetLogger(path.parent, enabled=True, secrets=(
        os.getenv("GEMINI_API_KEY"), os.getenv("OPENAI_API_KEY")))
    # Reject secret-bearing artifacts rather than silently changing training text.
    if logger.safe(payload) != payload:
        raise ValueError("Artifact contains credential-like text; sanitize before saving")
    if path.exists() and not replace:
        if read_rows(path) == payload:
            return
        raise ValueError("Artifact already exists with different content; use a new output path")
    logger._write(path, payload)


@contextmanager
def exclusive_writer(path: Path):
    """A crash leaves a lock for explicit inspection, preventing concurrent calls."""
    guard_output(path)
    lock = Path(str(path) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        stream = lock.open("x", encoding="utf-8")
    except FileExistsError:
        raise ValueError("Writer lock exists; stop other writers before removing a stale .lock") from None
    try:
        with stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)
