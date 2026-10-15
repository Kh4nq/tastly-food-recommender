"""Opt-in pytest guard: skip sealed-data readers and reject unexpected opens.

Run: python -m pytest -q -p scripts.sealed_benchmark_guard
This leaves tests and benchmark semantics unchanged for their owners.
"""
import os
from pathlib import Path
import sys

import pytest

SEALED = os.path.normcase(str(Path(__file__).resolve().parents[1] / "benchmarks/ai2_vietnamese_prompts.jsonl"))


def _guard(event, args):
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        path = os.path.normcase(os.path.abspath(os.fsdecode(args[0])))
        if path == SEALED:
            raise PermissionError("Sealed benchmark access is forbidden in this regression run")


sys.addaudithook(_guard)


def pytest_collection_modifyitems(items):
    readers = {
        "test_dataset_valid_balanced_without_running_benchmark",
        "test_benchmark_category_selection", "test_benchmark_limit_after_selection",
        "test_list_categories_without_config_or_provider", "test_benchmark_selection_report_offline",
    }
    for item in items:
        name = item.originalname or item.name
        reads_sealed = item.path.name == "test_ai2_tools.py" and name in readers
        if item.path.name == "test_ai2_tools.py" and name == "test_benchmark_selection_errors_before_provider":
            reads_sealed = "nonexistent" in item.callspec.params["argv"]
        if item.path.name == "test_ai2_labeling.py":
            reads_sealed = name in {
                "test_actual_benchmark_is_excluded_before_teacher",
                "test_offline_orchestrator_resume_export_and_cli_stats",
                "test_individual_cli_stages_and_invalid_exit",
            }
        if item.path.name == "test_ai2_labeling_ui.py":
            reads_sealed = "app" in item.fixturenames
        if item.path.name == "test_openai_provider.py":
            reads_sealed = name == "test_benchmark_and_smoke_offline"
        if reads_sealed:
            item.add_marker(pytest.mark.skip(reason="Sealed benchmark: no inspection or execution authorized"))
