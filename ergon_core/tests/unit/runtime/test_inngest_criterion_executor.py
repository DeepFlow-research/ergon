"""Contracts for Inngest criterion executor runtime wiring."""

from uuid import uuid4

import pytest
from ergon_core.api.criterion import Criterion
from ergon_core.api.criterion import CriterionContext
from ergon_core.api.criterion import CriterionOutcome
from ergon_core.test_support.task_factory import task_with_id
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

    slug: str = "criterion"
    observed_runtime: bool = False

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
        self.observed_runtime = context.has_runtime
        return CriterionOutcome(name=self.slug, score=1.0, passed=True)


@pytest.mark.asyncio
async def test_executor_scopes_criterion_runtime_to_task_execution(monkeypatch) -> None:
    execution_id = uuid4()
    task_id = uuid4()
    captured_options = []

    class FakeRuntime:
        def __init__(self, *, context, sandbox_manager, options) -> None:
            captured_options.append(options)
            self.task_scope = options.task_id

    monkeypatch.setattr(
        "ergon_core.core.application.evaluation.inngest_executor.DefaultCriterionRuntime",
        FakeRuntime,
    )

    criterion = _Criterion()
    executor = InngestCriterionExecutor(
        _Ctx(),
        task_id=task_id,
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
        task_with_id(
            uuid4(),
            task_slug="task",
            instance_key="default",
            description="input",
            evaluator_binding_keys=("default",),
        ),
        "benchmark",
        [CriterionSpec(criterion=criterion)],
    )

    assert captured_options[0].task_id == execution_id
    assert criterion.observed_runtime is True
