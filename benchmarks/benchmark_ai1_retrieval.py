from __future__ import annotations

import statistics
import time
import tracemalloc

from retrieval.retriever import Retriever


RUNS = 5
TOP_K = 100

# Broad positive semantic query with no hard constraints.
STATE = {
    "location": None,
    "hard_constraints": {},
    "food": ["food"],
    "cuisine": [],
    "soft_preferences": {},
    "semantic_preferences": [],
    "negative_preferences": [],
    "reference_restaurants": [],
    "context": {},
}


def main():
    tracemalloc.start()

    init_start = time.perf_counter()
    retriever = Retriever()
    init_seconds = time.perf_counter() - init_start

    # Warm-up: includes first model use/load if needed.
    warmup_start = time.perf_counter()
    warmup = retriever.retrieve_frame(STATE, top_k=TOP_K)
    warmup_seconds = time.perf_counter() - warmup_start

    latencies = []

    for _ in range(RUNS):
        start = time.perf_counter()
        result = retriever.retrieve_frame(STATE, top_k=TOP_K)
        latencies.append(time.perf_counter() - start)

    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print("AI1 broad-query benchmark")
    print(f"candidate_top_k: {TOP_K}")
    print(f"runs: {RUNS}")
    print(f"returned_rows: {len(result)}")
    print(f"warmup_rows: {len(warmup)}")
    print(f"init_seconds: {init_seconds:.4f}")
    print(f"warmup_seconds: {warmup_seconds:.4f}")
    print(f"mean_seconds: {statistics.mean(latencies):.4f}")
    print(f"median_seconds: {statistics.median(latencies):.4f}")
    print(f"min_seconds: {min(latencies):.4f}")
    print(f"max_seconds: {max(latencies):.4f}")
    print(f"peak_tracemalloc_mb: {peak_bytes / 1024 / 1024:.2f}")


if __name__ == "__main__":
    main()