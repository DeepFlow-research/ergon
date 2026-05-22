"""MiniF2F v2 authoring shape: toolkit round-trip and task JSON assertions."""

from ergon_builtins.benchmarks.minif2f.worker_factory import (
    make_minif2f_rubric,
    make_minif2f_worker,
)
from ergon_builtins.benchmarks.minif2f.sandbox import LeanSandbox
from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit


def test_minif2f_toolkit_round_trips_through_json() -> None:
    tk = MiniF2FToolkit(max_tool_calls=16)
    serialized = tk.model_dump(mode="json")
    assert serialized["_type"].endswith(":MiniF2FToolkit")
    rebuilt = MiniF2FToolkit.model_validate(serialized)
    assert rebuilt.max_tool_calls == 16


def test_lean_sandbox_serializes_with_type_discriminator() -> None:
    sb = LeanSandbox()
    serialized = sb.model_dump(mode="json")
    assert serialized["_type"].endswith(":LeanSandbox")


def test_make_minif2f_worker_serializes_with_nested_toolkit_type() -> None:
    worker = make_minif2f_worker()
    serialized = worker.model_dump(mode="json")
    assert serialized["_type"].endswith(":ReActWorker"), serialized["_type"]
    toolkit_json = serialized.get("toolkit")
    assert toolkit_json is not None, "toolkit must be present in worker JSON"
    assert toolkit_json["_type"].endswith(":MiniF2FToolkit"), toolkit_json["_type"]


def test_make_minif2f_rubric_serializes_with_type_discriminator() -> None:
    rubric = make_minif2f_rubric()
    serialized = rubric.model_dump(mode="json")
    assert serialized["_type"].endswith(":MiniF2FRubric"), serialized["_type"]


def test_minif2f_task_json_has_correct_shape() -> None:
    """A MiniF2F Task serializes to the v2 object-bound shape."""
    from ergon_builtins.benchmarks.minif2f.benchmark import MiniF2FTask
    from ergon_builtins.benchmarks.minif2f.task_schemas import MiniF2FTaskPayload

    task = MiniF2FTask(
        task_slug="prove",
        instance_key="sample-1",
        description="Prove theorem sample-1.",
        task_payload=MiniF2FTaskPayload(
            name="sample-1",
            informal_statement="Prove 1+1=2.",
            formal_statement="theorem sample_1 : 1 + 1 = 2 := by",
            header="import Mathlib\n",
        ),
        worker=make_minif2f_worker(),
        sandbox=LeanSandbox(),
        evaluators=(make_minif2f_rubric(),),
    )
    task_json = task.model_dump(mode="json")

    assert task_json["worker"]["_type"].endswith(":ReActWorker")
    assert task_json["worker"]["toolkit"]["_type"].endswith(":MiniF2FToolkit")
    assert task_json["sandbox"]["_type"].endswith(":LeanSandbox")
    assert task_json["evaluators"], "evaluators must persist"
    assert all(ev.get("_type") for ev in task_json["evaluators"]), (
        "every evaluator entry must carry a `_type` discriminator"
    )
    assert "_legacy" not in task_json, (
        "MiniF2F is now object-bound; the _legacy bridge marker should be absent"
    )


def test_minif2f_benchmark_accepts_custom_worker_factory(monkeypatch) -> None:
    """The benchmark uses the worker_factory passed to its constructor.

    Load-bearing assertion: factories are *called*, not stored as a class
    attribute that defaults to them.  Without this test, a future refactor
    could accidentally revert to hardcoding the default and the test suite
    would still pass.
    """
    from unittest.mock import MagicMock

    from ergon_builtins.benchmarks.minif2f.benchmark import MiniF2FBenchmark
    from ergon_builtins.benchmarks.minif2f.task_schemas import MiniF2FProblem

    sentinel_worker = make_minif2f_worker()
    sentinel_worker.name = "sentinel"
    factory = MagicMock(return_value=sentinel_worker)

    # Stub out HF download so the test stays hermetic.
    monkeypatch.setattr(
        MiniF2FBenchmark,
        "_load_problems",
        lambda self: [
            MiniF2FProblem(
                name="x",
                informal_statement="i",
                formal_statement="theorem x : True := by",
                header="import Mathlib\n",
            )
        ],
    )

    benchmark = MiniF2FBenchmark(worker_factory=factory, limit=1)
    tasks = list(benchmark.build_instances().values())[0]

    assert tasks[0].worker is sentinel_worker
    factory.assert_called_once()
