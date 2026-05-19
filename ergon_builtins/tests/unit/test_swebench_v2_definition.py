"""SWE-Bench Verified v2 authoring shape: task JSON definition + reconstruction.

PR 10a: assert ``SweBenchVerifiedBenchmark`` returns ``Task`` instances
that serialize to the object-bound JSON shape (``_type`` on worker,
sandbox, every evaluator entry, no ``_legacy`` marker) and that the
snapshot round-trips through ``Task.from_definition``.

The benchmark's ``build_instances`` hits HuggingFace by default; we
monkeypatch ``_load_rows`` so the unit test stays offline.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from ergon_builtins.benchmarks.swebench_verified.benchmark import (
    SweBenchVerifiedBenchmark,
)
from ergon_builtins.benchmarks.swebench_verified.sandbox import SWEBenchSandbox
from ergon_builtins.benchmarks.swebench_verified.task_schemas import (
    SWEBenchInstance,
    SWEBenchTaskPayload,
)
from ergon_builtins.benchmarks.swebench_verified.toolkit import SWEBenchToolkit
from ergon_builtins.benchmarks.swebench_verified.workers import (
    make_swebench_rubric,
    make_swebench_worker,
)
from ergon_core.api.benchmark.task import Task


FAKE_ROW = {
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
}


def _fake_load_rows(*, limit=None):
    rows = [SWEBenchInstance.from_raw(FAKE_ROW)]
    return rows if limit is None else rows[:limit]


# ── Component-level serialization sanity ────────────────────────────────


def test_swebench_toolkit_round_trips_through_json() -> None:
    tk = SWEBenchToolkit(max_tool_calls=16)
    serialized = tk.model_dump(mode="json")
    assert serialized["_type"].endswith(":SWEBenchToolkit")
    rebuilt = SWEBenchToolkit.model_validate(serialized)
    assert rebuilt.max_tool_calls == 16


def test_swebench_sandbox_serializes_with_type_discriminator() -> None:
    sb = SWEBenchSandbox()
    serialized = sb.model_dump(mode="json")
    assert serialized["_type"].endswith(":SWEBenchSandbox")


def test_make_swebench_worker_serializes_with_nested_toolkit_type() -> None:
    worker = make_swebench_worker()
    serialized = worker.model_dump(mode="json")
    assert serialized["_type"].endswith(":ReActWorker"), serialized["_type"]
    toolkit_json = serialized.get("toolkit")
    assert toolkit_json is not None, "toolkit must be present in worker JSON"
    assert toolkit_json["_type"].endswith(":SWEBenchToolkit"), toolkit_json["_type"]


def test_make_swebench_rubric_serializes_with_type_discriminator() -> None:
    rubric = make_swebench_rubric()
    serialized = rubric.model_dump(mode="json")
    assert serialized["_type"].endswith(":SWEBenchRubric"), serialized["_type"]


# ── Task-level v2 shape ─────────────────────────────────────────────────


def test_swebench_task_json_has_v2_object_bound_shape() -> None:
    """A SWE-Bench Task serializes to the v2 object-bound shape."""
    with patch(
        "ergon_builtins.benchmarks.swebench_verified.benchmark._load_rows",
        side_effect=_fake_load_rows,
    ):
        benchmark = SweBenchVerifiedBenchmark(limit=1)
        task = benchmark.build_instances()["default"][0]

    task_json = task.model_dump(mode="json")

    assert task_json["worker"]["_type"].endswith(":ReActWorker")
    assert task_json["worker"]["toolkit"]["_type"].endswith(":SWEBenchToolkit")
    assert task_json["sandbox"]["_type"].endswith(":SWEBenchSandbox")
    assert task_json["evaluators"], "evaluators must persist"
    assert all(ev.get("_type") for ev in task_json["evaluators"]), (
        "every evaluator entry must carry a `_type` discriminator"
    )
    assert "_legacy" not in task_json, (
        "SWE-Bench is now object-bound; the _legacy bridge marker should be absent"
    )


def test_swebench_benchmark_accepts_custom_worker_factory() -> None:
    """The benchmark uses the worker_factory passed to its constructor."""
    from unittest.mock import MagicMock

    sentinel_worker = make_swebench_worker()
    sentinel_worker.name = "sentinel"
    factory = MagicMock(return_value=sentinel_worker)

    with patch(
        "ergon_builtins.benchmarks.swebench_verified.benchmark._load_rows",
        side_effect=_fake_load_rows,
    ):
        benchmark = SweBenchVerifiedBenchmark(worker_factory=factory, limit=1)
        tasks = list(benchmark.build_instances().values())[0]

    assert tasks[0].worker is sentinel_worker
    factory.assert_called_once()


@pytest.mark.asyncio
async def test_swebench_task_json_round_trips_through_from_definition() -> None:
    """Definition JSON inflates back to a Task whose sandbox is SWEBenchSandbox."""
    with patch(
        "ergon_builtins.benchmarks.swebench_verified.benchmark._load_rows",
        side_effect=_fake_load_rows,
    ):
        benchmark = SweBenchVerifiedBenchmark(limit=1)
        task = benchmark.build_instances()["default"][0]

    task_json = task.model_dump(mode="json")

    rebuilt = await Task.from_definition(task_json, task_id=uuid4())

    assert rebuilt.worker is not None
    assert rebuilt.sandbox is not None
    assert isinstance(rebuilt.sandbox, type(task.sandbox))
    assert rebuilt.evaluators
    assert all(ev is not None for ev in rebuilt.evaluators)
