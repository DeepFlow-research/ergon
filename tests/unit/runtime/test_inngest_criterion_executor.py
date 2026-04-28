"""Contracts for Inngest criterion executor runtime wiring."""

from uuid import uuid4

import pytest
from ergon_core.api.criterion import Criterion
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.results import CriterionResult
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.core.runtime.evaluation.evaluation_schemas import (
    CriterionSpec,
    TaskEvaluationContext,
)
from ergon_core.core.runtime.evaluation.inngest_executor import InngestCriterionExecutor


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
        super().__init__(name="criterion")
        self.runtime_task_scope = None

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        self.runtime_task_scope = context.runtime.task_scope
        return CriterionResult(name=self.name, score=1.0, passed=True)


@pytest.mark.asyncio
async def test_executor_scopes_criterion_runtime_to_task_execution(monkeypatch) -> None:
    execution_id = uuid4()
    definition_task_id = uuid4()
    captured_options = []

    class FakeRuntime:
        def __init__(self, *, context, sandbox_manager, options) -> None:
            captured_options.append(options)
            self.task_scope = options.task_id

    monkeypatch.setattr(
        "ergon_core.core.runtime.evaluation.inngest_executor.DefaultCriterionRuntime",
        FakeRuntime,
    )

    criterion = _Criterion()
    executor = InngestCriterionExecutor(
        _Ctx(),
        task_id=definition_task_id,
        execution_id=execution_id,
        evaluator_id=uuid4(),
        sandbox_manager=object(),
    )

    await executor.execute_all(
        TaskEvaluationContext(
            run_id=uuid4(),
            task_input="input",
            agent_reasoning="output",
        ),
        BenchmarkTask(
            task_slug="task",
            instance_key="default",
            description="input",
            evaluator_binding_keys=("default",),
        ),
        "benchmark",
        [CriterionSpec(criterion=criterion)],
    )

    assert captured_options[0].task_id == execution_id
    assert criterion.runtime_task_scope == execution_id
