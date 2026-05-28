"""Round-trip contracts for migrated builtin object-bound tasks."""

from collections.abc import Sequence
from uuid import uuid4

import pytest

from ergon_builtins.agents.react.worker import ReActWorker
from ergon_builtins.benchmarks.gdpeval.prompts import GDPEVAL_SYSTEM_PROMPT
from ergon_builtins.benchmarks.gdpeval.rubric import StagedRubric
from ergon_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandbox
from ergon_builtins.benchmarks.gdpeval.sample import make_gdpeval_sample
from ergon_builtins.benchmarks.gdpeval.task_schemas import GDPTaskConfig
from ergon_builtins.benchmarks.gdpeval.toolkit import GDPEvalToolkit
from ergon_builtins.benchmarks.minif2f.prompts import MINIF2F_SYSTEM_PROMPT
from ergon_builtins.benchmarks.minif2f.rubric import MiniF2FRubric
from ergon_builtins.benchmarks.minif2f.sandbox import LeanSandbox
from ergon_builtins.benchmarks.minif2f.sample import make_minif2f_sample
from ergon_builtins.benchmarks.minif2f.task_schemas import MiniF2FProblem
from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit
from ergon_builtins.benchmarks.researchrubrics.prompts import RESEARCH_SYSTEM_PROMPT
from ergon_builtins.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from ergon_builtins.benchmarks.researchrubrics.sandbox import ResearchE2BSandbox
from ergon_builtins.benchmarks.researchrubrics.sample import make_researchrubrics_sample
from ergon_builtins.benchmarks.researchrubrics.task_schemas import (
    ResearchRubricsTaskPayload,
    RubricCriterion,
)
from ergon_builtins.benchmarks.researchrubrics.toolkit import ResearchRubricsToolkit
from ergon_builtins.benchmarks.swebench_verified.prompts import SWEBENCH_SYSTEM_PROMPT
from ergon_builtins.benchmarks.swebench_verified.rubric import SWEBenchRubric
from ergon_builtins.benchmarks.swebench_verified.sandbox import SWEBenchSandbox
from ergon_builtins.benchmarks.swebench_verified.sample import make_swebench_sample
from ergon_builtins.benchmarks.swebench_verified.task_schemas import SWEBenchInstance
from ergon_builtins.benchmarks.swebench_verified.toolkit import SWEBenchToolkit
from ergon_core.api.task import Task
from ergon_core.api.rubric import Rubric


@pytest.fixture
def builtin_tasks() -> Sequence[Task]:
    mini_worker = ReActWorker(
        name="mini-proof-solver",
        model="test:none",
        system_prompt=MINIF2F_SYSTEM_PROMPT,
        max_iterations=30,
        toolkit=MiniF2FToolkit(),
    )
    swe_worker = ReActWorker(
        name="swebench-solver",
        model="test:none",
        system_prompt=SWEBENCH_SYSTEM_PROMPT,
        max_iterations=50,
        toolkit=SWEBenchToolkit(),
    )
    research_worker = ReActWorker(
        name="research-runner",
        model="test:none",
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        max_iterations=16,
        toolkit=ResearchRubricsToolkit(),
    )
    gdp_worker = ReActWorker(
        name="gdpeval-runner",
        model="test:none",
        system_prompt=GDPEVAL_SYSTEM_PROMPT,
        max_iterations=40,
        toolkit=GDPEvalToolkit(),
    )
    return (
        make_minif2f_sample(
            MiniF2FProblem(
                name="mini-sample",
                informal_statement="Prove that one equals one.",
                formal_statement="theorem mini_sample : 1 = 1 := by",
                header="import Mathlib\n",
            ),
            environment_name="minif2f",
            worker=mini_worker,
            evaluators=[MiniF2FRubric(name="minif2f-rubric")],
            sandbox=LeanSandbox(),
        ).tasks[0],
        make_swebench_sample(
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
            ),
            environment_name="swebench-verified",
            worker=swe_worker,
            evaluators=[SWEBenchRubric(name="swebench-rubric")],
            sandbox=SWEBenchSandbox(),
        ).tasks[0],
        make_researchrubrics_sample(
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
            ),
            environment_name="researchrubrics",
            worker=research_worker,
            evaluators=[ResearchRubricsRubric(name="researchrubrics-rubric")],
            sandbox=ResearchE2BSandbox(),
        ).tasks[0],
        make_gdpeval_sample(
            GDPTaskConfig(
                task_id="gdp-sample-1",
                workflow_type="document_processing",
                reference_files=["/tmp/reference.pdf"],
            ),
            environment_name="gdpeval",
            worker=gdp_worker,
            evaluators=[
                StagedRubric(
                    name="gdpeval-staged-rubric",
                    category_name="default",
                    max_total_score=1.0,
                )
            ],
            sandbox=GDPEvalSandbox(),
            task_description=lambda _row: "Create a summary document.",
        ).tasks[0],
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
