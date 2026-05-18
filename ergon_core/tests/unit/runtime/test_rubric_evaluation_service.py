"""Contracts for rubric evaluation service spec construction."""

import pytest
from uuid import uuid4

from ergon_core.api.criterion import Criterion
from ergon_core.api.criterion import CriterionContext
from ergon_core.api.rubric import Rubric
from ergon_core.api.criterion import CriterionOutcome, ScoreScale
from ergon_core.api.worker import WorkerOutput
from ergon_core.test_support.task_factory import task_with_id
from ergon_core.core.application.evaluation.service import (
    EvaluationService,
)


class _Criterion(Criterion):
    type_slug = "test-criterion"

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
        return CriterionOutcome(name=self.slug, score=self.score_spec.max_score, passed=True)


@pytest.mark.asyncio
async def test_rubric_service_uses_criterion_max_score_not_signed_weight() -> None:
    service = EvaluationService()
    evaluator = Rubric(
        name="rubric",
        criteria=[
            _Criterion(slug="positive", weight=2.0, score_spec=ScoreScale(max_score=2.0)),
            _Criterion(slug="negative", weight=-5.0, score_spec=ScoreScale(max_score=5.0)),
        ],
    )

    task = task_with_id(
        uuid4(),
        task_slug="task",
        instance_key="default",
        description="Task",
    )
    result = await service.evaluate(
        context=CriterionContext(
            run_id=uuid4(),
            task_id=task.task_id,
            execution_id=uuid4(),
            task=task,
            worker_result=WorkerOutput(output="", success=True),
        ),
        evaluator=evaluator,
    )

    assert [spec.max_score for spec in result.specs] == [2.0, 5.0]
