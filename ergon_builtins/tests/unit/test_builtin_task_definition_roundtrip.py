"""Round-trip contracts for migrated builtin object-bound tasks."""

from collections.abc import Sequence
from uuid import uuid4

import pytest

from ergon_builtins.benchmarks.gdpeval.benchmark import GDPEvalBenchmark
from ergon_builtins.benchmarks.gdpeval.task_schemas import GDPTaskConfig
from ergon_builtins.benchmarks.minif2f.benchmark import MiniF2FBenchmark
from ergon_builtins.benchmarks.minif2f.task_schemas import MiniF2FProblem
from ergon_builtins.benchmarks.researchrubrics.benchmark import ResearchRubricsBenchmark
from ergon_builtins.benchmarks.researchrubrics.task_schemas import (
    ResearchRubricsTaskPayload,
    RubricCriterion,
)
from ergon_builtins.benchmarks.swebench_verified.benchmark import SweBenchVerifiedBenchmark
from ergon_builtins.benchmarks.swebench_verified.task_schemas import SWEBenchInstance
from ergon_core.api.benchmark.task import Task
from ergon_core.api.rubric import Rubric


def _only_task(benchmark) -> Task:
    instances = benchmark.build_instances()
    return list(instances.values())[0][0]


@pytest.fixture
def builtin_tasks(monkeypatch: pytest.MonkeyPatch) -> Sequence[Task]:
    monkeypatch.setattr(
        MiniF2FBenchmark,
        "_load_problems",
        lambda self: [
            MiniF2FProblem(
                name="mini-sample",
                informal_statement="Prove that one equals one.",
                formal_statement="theorem mini_sample : 1 = 1 := by",
                header="import Mathlib\n",
            )
        ],
    )

    monkeypatch.setattr(
        "ergon_builtins.benchmarks.swebench_verified.benchmark._load_rows",
        lambda *, limit=None: [
            SWEBenchInstance(
                instance_id="repo__sample-1",
                repo="org/repo",
                base_commit="abcdef123456",
                problem_statement="Fix the failing parser.",
                version="1.0",
                fail_to_pass=["tests/test_parser.py::test_fix"],
                pass_to_pass=[],
                environment_setup_commit="abcdef123456",
                test_patch="diff --git a/tests/test_parser.py b/tests/test_parser.py\n",
            )
        ],
    )

    monkeypatch.setattr(
        ResearchRubricsBenchmark,
        "_load_rows",
        lambda self: [
            ResearchRubricsTaskPayload(
                sample_id="rr-sample-1",
                domain="quality",
                prompt="Write a short report.",
                rubrics=[
                    RubricCriterion(
                        criterion="Includes findings.",
                        axis="Communication Quality",
                        weight=2.0,
                    )
                ],
            )
        ],
    )

    monkeypatch.setattr(
        GDPEvalBenchmark,
        "_load_task_configs",
        lambda self: [
            GDPTaskConfig(
                task_id="gdp-sample-1",
                workflow_type="document_processing",
                reference_files=["/tmp/reference.pdf"],
            )
        ],
    )
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.gdpeval.benchmark.extract_task_description",
        lambda task_id, *, repo_id: "Create a summary document.",
    )

    return (
        _only_task(MiniF2FBenchmark(limit=1)),
        _only_task(SweBenchVerifiedBenchmark(limit=1)),
        _only_task(ResearchRubricsBenchmark(limit=1)),
        _only_task(GDPEvalBenchmark(limit=1)),
    )


@pytest.mark.asyncio
async def test_builtin_tasks_round_trip_concrete_object_bound_components(
    builtin_tasks: Sequence[Task],
) -> None:
    criteria_backed_rubrics = 0
    for task in builtin_tasks:
        dumped = task.model_dump(mode="json")
        loaded = await Task.from_definition(dumped, task_id=uuid4())

        assert loaded.worker is not None
        assert loaded.sandbox is not None
        assert loaded.evaluators
        assert type(loaded) is type(task)
        assert type(loaded.worker) is type(task.worker)
        assert type(loaded.worker.toolkit) is type(task.worker.toolkit)
        assert type(loaded.sandbox) is type(task.sandbox)
        assert [type(ev) for ev in loaded.evaluators] == [type(ev) for ev in task.evaluators]

        for original, rebuilt in zip(task.evaluators, loaded.evaluators, strict=True):
            if isinstance(original, Rubric) and original.criteria:
                criteria_backed_rubrics += 1
                assert rebuilt.criteria
                assert [type(c) for c in rebuilt.criteria] == [type(c) for c in original.criteria]
    assert criteria_backed_rubrics >= 3


def test_builtin_task_snapshots_use_importable_task_type(builtin_tasks: Sequence[Task]) -> None:
    for task in builtin_tasks:
        dumped = task.model_dump(mode="json")

        assert "[" not in dumped["_type"]
        assert "]" not in dumped["_type"]
