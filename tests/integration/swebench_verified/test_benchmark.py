"""Tests for the SWE-Bench Verified benchmark loader."""

from __future__ import annotations

from unittest.mock import patch

from ergon_builtins.benchmarks.swebench_verified.benchmark import (
    SweBenchVerifiedBenchmark,
)


def _fake_load_rows(*, limit=None):
    return FAKE_ROWS if limit is None else FAKE_ROWS[:limit]


FAKE_ROWS = [
    {
        "instance_id": "django__django-1",
        "repo": "django/django",
        "base_commit": "aaa",
        "patch": "GOLD",
        "test_patch": "TP1",
        "problem_statement": "p1",
        "hints_text": "",
        "version": "3.0",
        "FAIL_TO_PASS": '["t1"]',
        "PASS_TO_PASS": '["t0"]',
        "environment_setup_commit": "aaa",
    },
    {
        "instance_id": "sympy__sympy-2",
        "repo": "sympy/sympy",
        "base_commit": "bbb",
        "patch": "GOLD",
        "test_patch": "TP2",
        "problem_statement": "p2",
        "hints_text": "",
        "version": "1.10",
        "FAIL_TO_PASS": '["t2"]',
        "PASS_TO_PASS": '["t0"]',
        "environment_setup_commit": "bbb",
    },
]


def test_build_instances_yields_one_task_per_row() -> None:
    with patch(
        "ergon_builtins.benchmarks.swebench_verified.benchmark._load_rows",
        side_effect=_fake_load_rows,
    ):
        benchmark = SweBenchVerifiedBenchmark()
        instances = benchmark.build_instances()

    assert set(instances.keys()) == {"default"}
    tasks = instances["default"]
    assert len(tasks) == 2
    assert tasks[0].task_slug == "django__django-1"
    assert tasks[1].task_slug == "sympy__sympy-2"


def test_limit_truncates() -> None:
    with patch(
        "ergon_builtins.benchmarks.swebench_verified.benchmark._load_rows",
        side_effect=_fake_load_rows,
    ):
        benchmark = SweBenchVerifiedBenchmark(limit=1)
        tasks = benchmark.build_instances()["default"]

    assert len(tasks) == 1
    assert tasks[0].task_slug == "django__django-1"


def test_task_description_excludes_test_patch_and_gold_patch() -> None:
    with patch(
        "ergon_builtins.benchmarks.swebench_verified.benchmark._load_rows",
        side_effect=_fake_load_rows,
    ):
        benchmark = SweBenchVerifiedBenchmark()
        task = benchmark.build_instances()["default"][0]

    assert "TP1" not in task.description
    assert "GOLD" not in task.description
    assert "p1" in task.description


def test_task_payload_retains_test_patch_for_evaluator() -> None:
    with patch(
        "ergon_builtins.benchmarks.swebench_verified.benchmark._load_rows",
        side_effect=_fake_load_rows,
    ):
        benchmark = SweBenchVerifiedBenchmark()
        task = benchmark.build_instances()["default"][0]

    assert task.task_payload.test_patch == "TP1"
    assert not hasattr(task.task_payload, "patch")
