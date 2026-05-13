"""Contracts for rubric evaluation service spec construction."""

import pytest
from uuid import uuid4

from ergon_core.api.criterion import Criterion
from ergon_core.api.criterion import CriterionContext
from ergon_core.api.rubric import Rubric
from ergon_core.api.criterion import CriterionOutcome, ScoreScale
from ergon_core.api.benchmark import Task
from ergon_core.test_support.task_factory import task_with_id
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
            weight=weight,
            score_spec=ScoreScale(max_score=max_score),
        )

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
        return CriterionOutcome(name=self.slug, score=self.score_spec.max_score, passed=True)


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
                weight=spec.criterion.weight,
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
            _Criterion(slug="positive", weight=2.0, max_score=2.0),
            _Criterion(slug="negative", weight=-5.0, max_score=5.0),
        ],
    )

    await service.evaluate_legacy(
        TaskEvaluationContext(
            run_id=uuid4(),
            task_input="",
            agent_reasoning=None,
        ),
        evaluator,
        task_with_id(
            uuid4(),
            task_slug="task",
            instance_key="default",
            description="Task",
            evaluator_binding_keys=("default",),
        ),
        "benchmark",
    )

    assert [spec.max_score for spec in executor.seen_specs] == [2.0, 5.0]
