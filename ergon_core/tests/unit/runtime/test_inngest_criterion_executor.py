"""Contracts for Inngest criterion executor runtime wiring."""

from uuid import uuid4
from typing import AsyncGenerator, ClassVar

import pytest
from ergon_core.api import Sandbox, Worker, WorkerContext, WorkerOutput
from ergon_core.api.benchmark import Task
from ergon_core.api.criterion import Criterion
from ergon_core.api.criterion import CriterionContext
from ergon_core.api.criterion import CriterionOutcome
from ergon_core.core.application.evaluation.models import (
    CriterionSpec,
    TaskEvaluationContext,
)
from ergon_core.core.application.evaluation.inngest_executor import InngestCriterionExecutor


class _Step:
    async def run(self, _name, fn, *, output_type):
        return await fn()


class _Group:
    async def parallel(self, fns):
        return [await fn() for fn in fns]


class _Ctx:
    step = _Step()
    group = _Group()


class _Criterion(Criterion):
    type_slug = "test-criterion"

    def __init__(self) -> None:
        super().__init__(slug="criterion")
        self.observed_sandbox = False

    async def evaluate(self, context: CriterionContext, *, sandbox: Sandbox) -> CriterionOutcome:
        self.observed_sandbox = isinstance(sandbox, Sandbox)
        return CriterionOutcome(name=self.slug, score=1.0, passed=True)


class _Sandbox(Sandbox):
    async def provision(self) -> None:
        return None


class _Worker(Worker):
    type_slug: ClassVar[str] = "criterion-executor-test-worker"

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
        sandbox: Sandbox,
    ) -> AsyncGenerator[WorkerOutput, None]:
        yield WorkerOutput(output="", success=True)


@pytest.mark.asyncio
async def test_executor_passes_task_sandbox_to_criterion() -> None:
    execution_id = uuid4()
    definition_task_id = uuid4()
    sandbox = _Sandbox()

    criterion = _Criterion()
    executor = InngestCriterionExecutor(
        _Ctx(),
        task_id=definition_task_id,
        execution_id=execution_id,
        evaluator_id=uuid4(),
        sandbox=sandbox,
    )

    await executor.execute_all(
        TaskEvaluationContext(
            run_id=uuid4(),
            task_input="input",
            agent_reasoning="output",
        ),
        Task(
            task_slug="task",
            instance_key="default",
            description="input",
            worker=_Worker(name="worker", model=None),
            sandbox=_Sandbox(),
            evaluators=(),
        ),
        "benchmark",
        [CriterionSpec(criterion=criterion)],
    )

    assert criterion.observed_sandbox is True
