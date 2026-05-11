"""Contracts for rubric evaluation service spec construction."""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest

from ergon_core.api import Sandbox, WeightedCriterion, Worker, WorkerContext, WorkerOutput
from ergon_core.api.benchmark import Task
from ergon_core.api.criterion import Criterion
from ergon_core.api.criterion import CriterionContext
from ergon_core.api.criterion import CriterionOutcome
from ergon_core.api.rubric import Rubric
from ergon_core.api.worker import WorkerStreamItem
from ergon_core.core.application.evaluation.models import (
    CriterionSpec,
    TaskEvaluationContext,
)
from ergon_core.core.application.evaluation.service import (
    EvaluationService,
)


class _Criterion(Criterion):
    type_slug = "test-criterion"

    def __init__(self, *, slug: str, weight: float, max_score: float) -> None:
        super().__init__(
            slug=slug,
            max_score=max_score,
        )

    async def evaluate(self, context: CriterionContext, *, sandbox: Sandbox) -> CriterionOutcome:
        return CriterionOutcome(name=self.slug, score=self.max_score, passed=True)


class _Sandbox(Sandbox):
    async def provision(self) -> None:
        pass


class _Worker(Worker):
    type_slug = "test-worker"

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
        sandbox: Sandbox,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        yield WorkerOutput(output=task.task_slug, success=True)


class _Executor:
    def __init__(self) -> None:
        self.seen_specs: list[CriterionSpec] = []

    async def execute_all(
        self,
        task_context: TaskEvaluationContext,
        task: Task,
        benchmark_name: str,
        criteria: list[CriterionSpec],
    ) -> list[CriterionOutcome]:
        self.seen_specs = criteria
        return [
            CriterionOutcome(
                name=spec.criterion.slug,
                score=spec.max_score,
                passed=True,
                weight=spec.aggregation_weight,
            )
            for spec in criteria
        ]


@pytest.mark.asyncio
async def test_rubric_service_uses_criterion_max_score_not_signed_weight() -> None:
    executor = _Executor()
    service = EvaluationService(executor)
    evaluator = Rubric(
        name="rubric",
        criteria=[
            WeightedCriterion(
                criterion=_Criterion(slug="positive", weight=2.0, max_score=2.0),
                weight=2.0,
            ),
            WeightedCriterion(
                criterion=_Criterion(slug="negative", weight=-5.0, max_score=5.0),
                weight=-5.0,
            ),
        ],
    )
    task_definition = Task(
        task_slug="task",
        instance_key="default",
        description="Task",
        worker=_Worker(name="worker", model="stub:model"),
        sandbox=_Sandbox(),
    )

    await service.evaluate(
        TaskEvaluationContext(
            run_id=uuid4(),
            task_input="",
            agent_reasoning=None,
        ),
        evaluator,
        Task.from_definition(task_definition.to_definition(), task_id=uuid4()),
        "benchmark",
    )

    assert [spec.max_score for spec in executor.seen_specs] == [2.0, 5.0]
    assert [spec.aggregation_weight for spec in executor.seen_specs] == [2.0, -5.0]
