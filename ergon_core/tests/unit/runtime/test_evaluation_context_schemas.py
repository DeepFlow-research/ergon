"""Contracts for the v2 task/evaluate wire schema."""

from uuid import uuid4

from pydantic import ValidationError
import pytest

from ergon_core.core.application.evaluation import models as evaluation_models
from ergon_core.core.application.jobs.models import TaskEvaluateRequest


def test_task_evaluate_request_is_id_only_with_evaluator_index() -> None:
    request = TaskEvaluateRequest(
        run_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        evaluator_index=1,
    )

    assert set(request.model_dump(mode="json")) == {
        "run_id",
        "task_id",
        "execution_id",
        "evaluator_index",
    }


def test_task_evaluate_request_requires_evaluator_index() -> None:
    with pytest.raises(ValidationError, match="evaluator_index"):
        TaskEvaluateRequest(
            run_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
        )


def test_internal_v1_dispatch_dtos_are_removed() -> None:
    removed = {
        "CriterionContext",
        "DispatchEvaluatorsCommand",
        "PreparedEvaluatorDispatch",
        "PreparedSingleEvaluator",
        "TaskEvaluationContext",
    }

    assert all(not hasattr(evaluation_models, name) for name in removed)
