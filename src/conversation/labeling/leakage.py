"""The held-out set is read only as an exclusion index, never as a generator."""
from collections import Counter
import hashlib
import re

from conversation._utils import normalize_text
from conversation.labeling.storage import BENCHMARK, read_rows


def normalized_message(message: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", normalize_text(message)).split())


def prompt_hash(message: str) -> str:
    return hashlib.sha256(normalized_message(message).encode("utf-8")).hexdigest()


class LeakageIndex:
    def __init__(self, messages):
        self.exact = set(messages)
        self.normalized = {prompt_hash(message) for message in self.exact}

    @classmethod
    def from_benchmark(cls, path=BENCHMARK):
        rows = read_rows(path)
        if not rows or any(not isinstance(r.get("message"), str) for r in rows):
            raise ValueError("Benchmark exclusion index is empty or malformed")
        return cls(row["message"] for row in rows)

    def overlap(self, sample):
        messages = [sample.message, *sample.history]
        if any(m in self.exact for m in messages):
            return "benchmark_exact_overlap"
        if any(prompt_hash(m) in self.normalized for m in messages):
            return "benchmark_normalized_overlap"
        return None


def pool_issues(samples, index):
    ids = Counter(s.sample_id for s in samples)
    exact = Counter(s.message for s in samples)
    normalized = Counter(prompt_hash(s.message) for s in samples)
    return [[code for code, present in (
        (index.overlap(s), bool(index.overlap(s))),
        ("duplicate_sample_id", ids[s.sample_id] > 1),
        ("duplicate_exact_message", exact[s.message] > 1),
        ("duplicate_normalized_message", normalized[prompt_hash(s.message)] > 1),
    ) if present] for s in samples]


def filter_pool(samples, index):
    accepted, excluded = [], []
    ids, exact, normalized = set(), set(), set()
    for sample in samples:
        key = prompt_hash(sample.message)
        reason = (index.overlap(sample) or
                  ("duplicate_sample_id" if sample.sample_id in ids else None) or
                  ("duplicate_exact_message" if sample.message in exact else None) or
                  ("duplicate_normalized_message" if key in normalized else None))
        if reason:
            excluded.append({"sample_id": sample.sample_id, "prompt_hash": key, "reason": reason})
        else:
            accepted.append(sample)
            ids.add(sample.sample_id)
            exact.add(sample.message)
            normalized.add(key)
    return accepted, excluded
