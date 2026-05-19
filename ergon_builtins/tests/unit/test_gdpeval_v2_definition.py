"""GDPEval v2 authoring shape: task JSON definition + reconstruction.

PR 10c: assert ``GDPEvalBenchmark`` returns ``Task`` instances that
serialize to the object-bound JSON shape (``_type`` on worker, sandbox,
every evaluator entry, no ``_legacy`` marker) and that the snapshot
round-trips through ``Task.from_definition``.

The benchmark's ``build_instances`` hits HuggingFace by default; we
monkeypatch ``_load_task_configs`` plus the ``extract_task_description``
loader call so the unit test stays offline.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from ergon_builtins.benchmarks.gdpeval.benchmark import GDPEvalBenchmark
from ergon_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandbox
from ergon_builtins.benchmarks.gdpeval.task_schemas import GDPTaskConfig
from ergon_builtins.benchmarks.gdpeval.toolkit import GDPEvalToolkit
from ergon_builtins.benchmarks.gdpeval.worker_factory import (
    make_gdpeval_rubric,
    make_gdpeval_worker,
)
from ergon_core.api.benchmark.task import Task


FAKE_PAYLOAD = GDPTaskConfig(
    task_id="gdpeval-fake-001",
    workflow_type="document_processing",
    reference_files=["/tmp/sample.pdf"],
)


def _fake_load_task_configs(self) -> list[GDPTaskConfig]:
    return [FAKE_PAYLOAD]


# ── Component-level serialization sanity ────────────────────────────────


def test_gdpeval_toolkit_round_trips_through_json() -> None:
    tk = GDPEvalToolkit(max_tool_calls=16)
    serialized = tk.model_dump(mode="json")
    assert serialized["_type"].endswith(":GDPEvalToolkit")
    rebuilt = GDPEvalToolkit.model_validate(serialized)
    assert rebuilt.max_tool_calls == 16


def test_gdpeval_sandbox_serializes_with_type_discriminator() -> None:
    sb = GDPEvalSandbox()
    serialized = sb.model_dump(mode="json")
    assert serialized["_type"].endswith(":GDPEvalSandbox")


def test_make_gdpeval_worker_serializes_with_nested_toolkit_type() -> None:
    worker = make_gdpeval_worker()
    serialized = worker.model_dump(mode="json")
    assert serialized["_type"].endswith(":ReActWorker"), serialized["_type"]
    toolkit_json = serialized.get("toolkit")
    assert toolkit_json is not None, "toolkit must be present in worker JSON"
    assert toolkit_json["_type"].endswith(":GDPEvalToolkit"), toolkit_json["_type"]


def test_make_gdpeval_rubric_serializes_with_type_discriminator() -> None:
    rubric = make_gdpeval_rubric()
    serialized = rubric.model_dump(mode="json")
    assert serialized["_type"].endswith(":StagedRubric"), serialized["_type"]


# ── Task-level v2 shape ─────────────────────────────────────────────────


def test_gdpeval_task_json_has_v2_object_bound_shape() -> None:
    """A GDPEval Task serializes to the v2 object-bound shape."""
    with (
        patch.object(GDPEvalBenchmark, "_load_task_configs", _fake_load_task_configs),
        patch(
            "ergon_builtins.benchmarks.gdpeval.benchmark.extract_task_description",
            lambda task_id, repo_id: "Process the reference document.",
        ),
    ):
        benchmark = GDPEvalBenchmark(limit=1)
        task = benchmark.build_instances()["default"][0]

    task_json = task.model_dump(mode="json")

    assert task_json["worker"]["_type"].endswith(":ReActWorker")
    assert task_json["worker"]["toolkit"]["_type"].endswith(":GDPEvalToolkit")
    assert task_json["sandbox"]["_type"].endswith(":GDPEvalSandbox")
    assert task_json["evaluators"], "evaluators must persist"
    assert all(ev.get("_type") for ev in task_json["evaluators"]), (
        "every evaluator entry must carry a `_type` discriminator"
    )
    assert task_json["evaluators"][0]["_type"].endswith(":StagedRubric")
    assert "_legacy" not in task_json, (
        "GDPEval is now object-bound; the _legacy bridge marker should be absent"
    )


def test_gdpeval_benchmark_accepts_custom_worker_factory() -> None:
    """The benchmark uses the worker_factory passed to its constructor."""
    from unittest.mock import MagicMock

    sentinel_worker = make_gdpeval_worker()
    sentinel_worker.name = "sentinel"
    factory = MagicMock(return_value=sentinel_worker)

    with (
        patch.object(GDPEvalBenchmark, "_load_task_configs", _fake_load_task_configs),
        patch(
            "ergon_builtins.benchmarks.gdpeval.benchmark.extract_task_description",
            lambda task_id, repo_id: "Process the reference document.",
        ),
    ):
        benchmark = GDPEvalBenchmark(worker_factory=factory, limit=1)
        tasks = list(benchmark.build_instances().values())[0]

    assert tasks[0].worker is sentinel_worker
    factory.assert_called_once()


@pytest.mark.asyncio
async def test_gdpeval_task_json_round_trips_through_from_definition() -> None:
    """Definition JSON inflates back to a Task whose sandbox is GDPEvalSandbox."""
    with (
        patch.object(GDPEvalBenchmark, "_load_task_configs", _fake_load_task_configs),
        patch(
            "ergon_builtins.benchmarks.gdpeval.benchmark.extract_task_description",
            lambda task_id, repo_id: "Process the reference document.",
        ),
    ):
        benchmark = GDPEvalBenchmark(limit=1)
        task = benchmark.build_instances()["default"][0]

    task_json = task.model_dump(mode="json")

    rebuilt = await Task.from_definition(task_json, task_id=uuid4())

    assert rebuilt.worker is not None
    assert rebuilt.sandbox is not None
    assert isinstance(rebuilt.sandbox, type(task.sandbox))
    assert rebuilt.evaluators
    assert all(ev is not None for ev in rebuilt.evaluators)
