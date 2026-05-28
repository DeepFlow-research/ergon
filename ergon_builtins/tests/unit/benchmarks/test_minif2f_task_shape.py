"""MiniF2F v2 authoring shape: toolkit round-trip and task JSON assertions."""

from ergon_builtins.agents.react.worker import ReActWorker
from ergon_builtins.benchmarks.minif2f.prompts import MINIF2F_SYSTEM_PROMPT
from ergon_builtins.benchmarks.minif2f.rubric import MiniF2FRubric
from ergon_builtins.benchmarks.minif2f.sandbox import LeanSandbox
from ergon_builtins.benchmarks.minif2f.sample import make_minif2f_sample
from ergon_builtins.benchmarks.minif2f.task_schemas import MiniF2FProblem
from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit


def _mini_worker() -> ReActWorker:
    return ReActWorker(
        name="mini-proof-solver",
        model="test:none",
        system_prompt=MINIF2F_SYSTEM_PROMPT,
        max_iterations=30,
        toolkit=MiniF2FToolkit(),
    )


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


def test_minif2f_worker_serializes_with_nested_toolkit_type() -> None:
    worker = _mini_worker()
    serialized = worker.model_dump(mode="json")
    assert serialized["_type"].endswith(":ReActWorker"), serialized["_type"]
    toolkit_json = serialized.get("toolkit")
    assert toolkit_json is not None, "toolkit must be present in worker JSON"
    assert toolkit_json["_type"].endswith(":MiniF2FToolkit"), toolkit_json["_type"]


def test_minif2f_rubric_serializes_with_type_discriminator() -> None:
    rubric = MiniF2FRubric(name="minif2f-rubric")
    serialized = rubric.model_dump(mode="json")
    assert serialized["_type"].endswith(":MiniF2FRubric"), serialized["_type"]


def test_minif2f_task_json_has_correct_shape() -> None:
    """A MiniF2F Task serializes to the v2 object-bound shape."""
    from ergon_builtins.benchmarks.minif2f.task import MiniF2FTask
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
        worker=_mini_worker(),
        sandbox=LeanSandbox(),
        evaluators=(MiniF2FRubric(name="minif2f-rubric"),),
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


def test_make_minif2f_sample_accepts_custom_worker() -> None:
    """The sample helper binds the worker passed to it.

    Load-bearing assertion: author-provided runtime components are used
    directly when rows are converted into samples.
    """

    sentinel_worker = _mini_worker()
    sentinel_worker.name = "sentinel"
    sample = make_minif2f_sample(
        MiniF2FProblem(
            name="x",
            informal_statement="i",
            formal_statement="theorem x : True := by",
            header="import Mathlib\n",
        ),
        environment_name="mini",
        worker=sentinel_worker,
        evaluators=[MiniF2FRubric(name="minif2f-rubric")],
        sandbox=LeanSandbox(),
    )

    assert sample.tasks[0].worker is sentinel_worker
