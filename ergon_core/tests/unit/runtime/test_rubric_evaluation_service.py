from collections.abc import Iterable
from uuid import uuid4

import pytest

from ergon_core.api.criterion import Criterion, CriterionContext
from ergon_core.api.criterion import CriterionOutcome, ScoreScale
from ergon_core.api.errors import DependencyError
from ergon_core.api.rubric import Evaluator, Rubric
from ergon_core.api.rubric.results import TaskEvaluationResult
from ergon_core.api.worker import WorkerOutput
from ergon_core.core.application.evaluation.models import CriterionSpec
from ergon_core.core.application.evaluation.service import (
    EvaluationService,
    EvaluationServiceResult,
    build_evaluation_summary,
)
from ergon_core.test_support.task_factory import task_with_id


class _Criterion(Criterion):
    type_slug = "test-criterion"

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
        return CriterionOutcome(
            slug=self.slug,
            name=self.slug,
            score=self.score_spec.max_score,
            passed=True,
        )


class _MissingDepsEvaluator(Evaluator):
    type_slug = "missing-deps-evaluator"
    required_packages = ["definitely_missing_ergon_eval_dep_17"]
    install_hint = "pip install definitely-missing-ergon-eval-dep-17"

    def criteria_for(self, task) -> Iterable[Criterion]:  # noqa: ANN001
        raise AssertionError("criteria_for should not run before evaluator dependencies validate")

    def aggregate_task(
        self,
        task,  # noqa: ANN001
        criterion_results: Iterable[CriterionOutcome],
    ) -> TaskEvaluationResult:
        raise AssertionError("aggregate_task should not run when evaluator dependencies are missing")


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


def test_evaluation_summary_uses_slug_when_outcome_name_is_absent() -> None:
    service_result = EvaluationServiceResult(
        result=TaskEvaluationResult(
            task_slug="task",
            score=1.0,
            passed=True,
            evaluator_name="rubric",
            criterion_results=[
                CriterionOutcome(
                    slug="slug-only",
                    score=1.0,
                    passed=True,
                ),
            ],
        ),
        specs=[
            CriterionSpec(
                criterion=_Criterion(slug="slug-only"),
                criterion_idx=0,
                max_score=1.0,
                stage_idx=0,
                stage_name="default",
                aggregation_weight=1.0,
            ),
        ],
    )

    summary = build_evaluation_summary(service_result, evaluation_input=None)

    assert summary.criterion_results[0].criterion_name == "slug-only"


@pytest.mark.asyncio
async def test_evaluator_dependencies_are_validated_before_criteria_resolution() -> None:
    service = EvaluationService()
    task = task_with_id(
        uuid4(),
        task_slug="task",
        instance_key="default",
        description="Task",
    )

    with pytest.raises(DependencyError, match="definitely_missing_ergon_eval_dep_17"):
        await service.evaluate(
            context=CriterionContext(
                run_id=uuid4(),
                task_id=task.task_id,
                execution_id=uuid4(),
                task=task,
                worker_result=WorkerOutput(output="", success=True),
            ),
            evaluator=_MissingDepsEvaluator(name="missing-deps"),
        )
