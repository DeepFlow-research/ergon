"""Built-in benchmarks emit object-bound Tasks for the authoring API redesign."""

from pathlib import Path

from ergon_core.api import Evaluator, Sandbox, Task, Worker

from ergon_builtins.benchmarks.gdpeval.benchmark import GDPEvalBenchmark
from ergon_builtins.benchmarks.gdpeval.task_schemas import GDPTaskConfig
from ergon_builtins.benchmarks.minif2f.benchmark import MiniF2FBenchmark
from ergon_builtins.benchmarks.minif2f.task_schemas import MiniF2FProblem
from ergon_builtins.benchmarks.researchrubrics.benchmark import ResearchRubricsBenchmark
from ergon_builtins.benchmarks.researchrubrics.task_schemas import (
    ResearchRubricsTaskPayload,
)
from ergon_builtins.benchmarks.swebench_verified.benchmark import SweBenchVerifiedBenchmark
from ergon_builtins.benchmarks.swebench_verified.task_schemas import SWEBenchInstance


def test_minif2f_tasks_bind_default_worker_sandbox_and_evaluator(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        MiniF2FBenchmark,
        "_load_problems",
        lambda self: [
            MiniF2FProblem(
                name="algebra",
                informal_statement="Prove a theorem.",
                formal_statement="theorem algebra : True := by trivial",
                header="import Mathlib",
            )
        ],
    )

    task = MiniF2FBenchmark().build_instances()["default"][0]

    _assert_bound_task(task)
    assert task.worker.type_slug == "react-v1"
    assert type(task.worker.toolkit).__name__ == "MiniF2FReActToolkit"
    assert type(task.sandbox).__name__ == "MiniF2FSandbox"
    assert task.evaluators[0].type_slug == "minif2f-rubric"


def test_swebench_tasks_bind_default_worker_sandbox_and_evaluator(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.swebench_verified.benchmark._load_rows",
        lambda limit: [
            SWEBenchInstance(
                instance_id="repo__project-1",
                repo="repo/project",
                base_commit="abc123",
                problem_statement="Fix the bug.",
                test_patch="diff --git a/test.py b/test.py",
                version="1.0",
                fail_to_pass=[],
                pass_to_pass=[],
                environment_setup_commit="abc123",
            )
        ],
    )

    task = SweBenchVerifiedBenchmark().build_instances()["default"][0]

    _assert_bound_task(task)
    assert task.worker.type_slug == "react-v1"
    assert type(task.worker.toolkit).__name__ == "SWEBenchReActToolkit"
    assert type(task.sandbox).__name__ == "SWEBenchSandbox"
    assert task.evaluators[0].type_slug == "swebench-rubric"


def test_gdpeval_tasks_bind_default_worker_sandbox_and_evaluator(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        GDPEvalBenchmark,
        "_load_task_configs",
        lambda self: [
            GDPTaskConfig(
                task_id="task_001",
                workflow_type="document_processing",
                reference_files=[str(Path("/tmp/reference.pdf"))],
            )
        ],
    )
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.gdpeval.benchmark.extract_task_description",
        lambda task_id, repo_id: "Process the reference document.",
    )

    task = GDPEvalBenchmark(dataset_repo="fake/repo").build_instances()["default"][0]

    _assert_bound_task(task)
    assert task.worker.type_slug == "react-v1"
    assert type(task.worker.toolkit).__name__ == "GDPEvalReActToolkit"
    assert type(task.sandbox).__name__ == "GDPEvalSandbox"
    assert task.evaluators[0].type_slug == "gdpeval-staged-rubric"


def test_researchrubrics_tasks_bind_default_worker_sandbox_and_evaluator(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        ResearchRubricsBenchmark,
        "_load_rows",
        lambda self: [
            ResearchRubricsTaskPayload(
                sample_id="sample-1",
                domain="science",
                prompt="Write a research report.",
                rubrics=[],
            )
        ],
    )

    task = ResearchRubricsBenchmark().build_instances()["default"][0]

    _assert_bound_task(task)
    assert task.worker.type_slug == "react-v1"
    assert type(task.worker.toolkit).__name__ == "ResearchRubricsWorkflowToolkit"
    assert type(task.sandbox).__name__ == "ResearchRubricsSandbox"
    assert task.evaluators[0].type_slug == "researchrubrics-rubric"


def _assert_bound_task(task: Task) -> None:
    assert isinstance(task.worker, Worker)
    assert isinstance(task.sandbox, Sandbox)
    assert task.evaluators
    assert all(isinstance(evaluator, Evaluator) for evaluator in task.evaluators)
    assert "evaluator_binding_keys" not in task.model_dump(mode="json")
