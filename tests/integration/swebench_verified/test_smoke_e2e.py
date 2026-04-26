"""End-to-end smoke for SWE-Bench Verified wiring (no LLM, no E2B, no HF)."""

from pathlib import Path
from unittest.mock import patch

from ergon_builtins.benchmarks.swebench_verified.benchmark import SweBenchVerifiedBenchmark
from ergon_builtins.benchmarks.swebench_verified.task_schemas import SWEBenchInstance
from ergon_builtins.evaluators.rubrics.swebench_rubric import SWEBenchRubric
from ergon_builtins.registry import (
    SANDBOX_TEMPLATES,
)

FAKE_ROW = {
    "instance_id": "django__django-1",
    "repo": "django/django",
    "base_commit": "aaa",
    "patch": "GOLD_PATCH_MUST_NOT_LEAK",
    "test_patch": "TP",
    "problem_statement": "Reproduce and fix.",
    "hints_text": "",
    "version": "3.0",
    "FAIL_TO_PASS": '["t1"]',
    "PASS_TO_PASS": '["t0"]',
    "environment_setup_commit": "aaa",
}


def test_sandbox_template_directory_is_packaged() -> None:
    template_dir: Path = SANDBOX_TEMPLATES["swebench-verified"]
    assert template_dir.is_dir()
    assert (template_dir / "Dockerfile").is_file()
    assert (template_dir / "e2b.toml.template").is_file()


def test_build_instances_strips_gold_patch_and_honors_limit() -> None:
    benchmark = SweBenchVerifiedBenchmark(limit=1)
    with patch(
        "ergon_builtins.benchmarks.swebench_verified.benchmark._load_rows",
        return_value=[SWEBenchInstance.from_raw(FAKE_ROW)],
    ):
        instances = benchmark.build_instances()

    tasks = instances["default"]
    assert len(tasks) == 1
    task = tasks[0]
    assert task.task_slug == "django__django-1"
    assert "GOLD_PATCH_MUST_NOT_LEAK" not in task.description
    # The task_payload should also be free of the gold patch
    payload_str = str(task.task_payload)
    assert "GOLD_PATCH_MUST_NOT_LEAK" not in payload_str


def test_rubric_instantiates_with_one_criterion() -> None:
    rubric = SWEBenchRubric(name="swebench-rubric")
    assert len(rubric.criteria) == 1
    assert rubric.criteria[0].name == "test-resolution"
    assert rubric.criteria[0].weight == 1.0
