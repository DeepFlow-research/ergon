from __future__ import annotations

from collections.abc import Iterable, Sequence

import pytest

from ergon_builtins.benchmarks.gdpeval.sample import make_gdpeval_sample
from ergon_builtins.benchmarks.gdpeval.task_schemas import GDPTaskConfig
from ergon_builtins.benchmarks.minif2f.sample import make_minif2f_sample
from ergon_builtins.benchmarks.minif2f.task_schemas import MiniF2FProblem
from ergon_builtins.benchmarks.researchrubrics.sample import make_researchrubrics_sample
from ergon_builtins.benchmarks.researchrubrics.task_schemas import (
    ResearchRubricsTaskPayload,
    RubricCriterion,
)
from ergon_builtins.benchmarks.swebench_verified.sample import make_swebench_sample
from ergon_builtins.benchmarks.swebench_verified.task_schemas import SWEBenchInstance
from ergon_core.api import Environment
from ergon_core.api.criterion import CriterionOutcome
from ergon_core.api.rubric import Evaluator, TaskEvaluationResult
from ergon_core.api.task import Task
from ergon_core.test_support.task_factory import TestSandbox, TestWorker


class TestEvaluator(Evaluator):
    type_slug = "test-evaluator"

    def criteria_for(self, task: Task) -> Iterable:
        return ()

    def aggregate_task(
        self,
        task: Task,
        criterion_results: Iterable[CriterionOutcome],
    ) -> TaskEvaluationResult:
        return TaskEvaluationResult(
            task_slug=task.task_slug,
            score=1.0,
            passed=True,
            evaluator_name=self.name,
            criterion_results=list(criterion_results),
        )


class FakeSweBenchRow(SWEBenchInstance):
    needs_ui: bool = False


@pytest.fixture
def worker() -> TestWorker:
    return TestWorker(name="worker", model="test:none")


@pytest.fixture
def robot_worker() -> TestWorker:
    return TestWorker(name="robot", model="test:none")


@pytest.fixture
def researcher_worker() -> TestWorker:
    return TestWorker(name="researcher", model="test:none")


@pytest.fixture
def evaluator() -> TestEvaluator:
    return TestEvaluator(name="judge")


@pytest.fixture
def ui_eval() -> TestEvaluator:
    return TestEvaluator(name="ui-judge")


@pytest.fixture
def patch_eval() -> TestEvaluator:
    return TestEvaluator(name="patch-judge")


@pytest.fixture
def sandbox() -> TestSandbox:
    return TestSandbox()


@pytest.fixture
def browser_sandbox() -> TestSandbox:
    return TestSandbox(env={"mode": "browser"})


@pytest.fixture
def repo_sandbox() -> TestSandbox:
    return TestSandbox(env={"mode": "repo"})


def fake_minif2f_rows() -> list[MiniF2FProblem]:
    return [
        MiniF2FProblem(
            name="mini-1",
            informal_statement="Prove one equals one.",
            formal_statement="theorem mini_1 : 1 = 1 := by",
            header="import Mathlib\n",
        ),
        MiniF2FProblem(
            name="mini-2",
            informal_statement="Prove two equals two.",
            formal_statement="theorem mini_2 : 2 = 2 := by",
            header="import Mathlib\n",
        ),
    ]


def fake_swebench_rows() -> list[FakeSweBenchRow]:
    return [
        FakeSweBenchRow(
            instance_id="swe-1",
            repo="org/repo",
            base_commit="abcdef123456",
            problem_statement="Fix the parser.",
            version="1.0",
            fail_to_pass=["tests/test_parser.py::test_fix"],
            pass_to_pass=[],
            environment_setup_commit="abcdef123456",
            test_patch="diff --git a/tests/test_parser.py b/tests/test_parser.py\n",
        ),
        FakeSweBenchRow(
            instance_id="swe-2",
            repo="org/repo",
            base_commit="abcdef123456",
            problem_statement="Fix the lexer.",
            version="1.0",
            fail_to_pass=["tests/test_lexer.py::test_fix"],
            pass_to_pass=[],
            environment_setup_commit="abcdef123456",
            test_patch="diff --git a/tests/test_lexer.py b/tests/test_lexer.py\n",
        ),
    ]


def fake_researchrubrics_rows() -> list[ResearchRubricsTaskPayload]:
    return [
        ResearchRubricsTaskPayload(
            sample_id="research-1",
            domain="analysis",
            prompt="Write a concise market analysis.",
            rubrics=[
                RubricCriterion(
                    criterion="Includes a clear conclusion.",
                    axis="Communication Quality",
                    weight=1.0,
                )
            ],
        ),
        ResearchRubricsTaskPayload(
            sample_id="research-2",
            domain="analysis",
            prompt="Write a concise technical analysis.",
            rubrics=[
                RubricCriterion(
                    criterion="Cites relevant evidence.",
                    axis="References & Citation Quality",
                    weight=1.0,
                )
            ],
        ),
    ]


def fake_gdpeval_rows() -> list[GDPTaskConfig]:
    return [
        GDPTaskConfig(
            task_id="gdp-1",
            workflow_type="document_processing",
            reference_files=["/tmp/reference-1.pdf"],
        ),
        GDPTaskConfig(
            task_id="gdp-2",
            workflow_type="document_processing",
            reference_files=["/tmp/reference-2.pdf"],
        ),
    ]


def build_row_backed_minif2f_environment(
    *,
    limit: int | None = None,
    worker: TestWorker | None = None,
    evaluators: Sequence[TestEvaluator] | None = None,
    sandbox: TestSandbox | None = None,
    rows: Sequence[MiniF2FProblem] | None = None,
):
    selected_rows = list(rows or fake_minif2f_rows())[:limit]
    env_name = "minif2f"
    return Environment.from_records(
        name=env_name,
        records=selected_rows,
        make_sample=lambda row: make_minif2f_sample(
            row,
            environment_name=env_name,
            worker=worker or TestWorker(name="worker", model="test:none"),
            evaluators=evaluators or [TestEvaluator(name="judge")],
            sandbox=sandbox or TestSandbox(),
        ),
    )


def build_row_backed_swebench_environment(
    *,
    limit: int | None = None,
    streaming: bool = False,
    worker=None,
    evaluators=None,
    sandbox=None,
    rows: Sequence[FakeSweBenchRow] | None = None,
):
    selected_rows = list(rows or fake_swebench_rows())[:limit]
    env_name = "swebench-verified"

    def make_sample(row: FakeSweBenchRow):
        resolved_worker = worker(row) if callable(worker) else worker
        resolved_evaluators = evaluators(row) if callable(evaluators) else evaluators
        resolved_sandbox = sandbox(row) if callable(sandbox) else sandbox
        return make_swebench_sample(
            row,
            environment_name=env_name,
            worker=resolved_worker or TestWorker(name="worker", model="test:none"),
            evaluators=resolved_evaluators or [TestEvaluator(name="judge")],
            sandbox=resolved_sandbox or TestSandbox(),
        )

    if streaming:
        return Environment.from_dataset(
            name=env_name,
            dataset=iter(selected_rows),
            source_mode="streaming",
            make_sample=make_sample,
        )
    return Environment.from_records(name=env_name, records=selected_rows, make_sample=make_sample)


def build_row_backed_researchrubrics_environment(
    *,
    limit: int | None = None,
    worker: TestWorker | None = None,
    evaluators: Sequence[TestEvaluator] | None = None,
    sandbox: TestSandbox | None = None,
    rows: Sequence[ResearchRubricsTaskPayload] | None = None,
):
    selected_rows = list(rows or fake_researchrubrics_rows())[:limit]
    env_name = "researchrubrics"
    return Environment.from_records(
        name=env_name,
        records=selected_rows,
        make_sample=lambda row: make_researchrubrics_sample(
            row,
            environment_name=env_name,
            worker=worker or TestWorker(name="worker", model="test:none"),
            evaluators=evaluators or [TestEvaluator(name="judge")],
            sandbox=sandbox or TestSandbox(),
        ),
    )


def build_row_backed_gdpeval_environment(
    *,
    limit: int | None = None,
    worker: TestWorker | None = None,
    evaluators: Sequence[TestEvaluator] | None = None,
    sandbox: TestSandbox | None = None,
    rows: Sequence[GDPTaskConfig] | None = None,
):
    selected_rows = list(rows or fake_gdpeval_rows())[:limit]
    env_name = "gdpeval"
    return Environment.from_records(
        name=env_name,
        records=selected_rows,
        make_sample=lambda row: make_gdpeval_sample(
            row,
            environment_name=env_name,
            worker=worker or TestWorker(name="worker", model="test:none"),
            evaluators=evaluators or [TestEvaluator(name="judge")],
            sandbox=sandbox or TestSandbox(),
            task_description=lambda config: f"Process {config.task_id}.",
        ),
    )


@pytest.fixture
def minif2f_environment_factory():
    return build_row_backed_minif2f_environment


@pytest.fixture
def swebench_environment_factory():
    return build_row_backed_swebench_environment


@pytest.fixture
def researchrubrics_environment_factory():
    return build_row_backed_researchrubrics_environment


@pytest.fixture
def gdpeval_environment_factory():
    return build_row_backed_gdpeval_environment
