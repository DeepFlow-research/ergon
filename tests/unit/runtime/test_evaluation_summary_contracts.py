"""Contracts for persisted evaluation summary nullability."""

from importlib import util
from pathlib import Path
from uuid import uuid4

import pytest
from ergon_core.api.criterion import Criterion
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.results import CriterionResult, TaskEvaluationResult
from ergon_core.core.persistence.telemetry.evaluation_summary import CriterionResultEntry
from ergon_core.core.runtime.evaluation.evaluation_schemas import CriterionSpec
from ergon_core.core.runtime.services.evaluation_persistence_service import (
    build_dashboard_evaluation_dto,
    build_evaluation_summary,
)
from ergon_core.core.runtime.services.rubric_evaluation_service import EvaluationServiceResult
from pydantic import ValidationError


class _Criterion(Criterion):
    type_slug = "test-criterion"

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        return CriterionResult(name=self.name, score=1.0, passed=True)


def _service_result(
    *,
    feedback: str | None,
    criterion_score: float = 1.0,
    criterion_weight: float = 1.0,
    passed: bool = True,
    metadata: dict | None = None,
) -> EvaluationServiceResult:
    criterion = _Criterion(name="Criterion description")
    return EvaluationServiceResult(
        result=TaskEvaluationResult(
            task_slug="task",
            score=criterion_score,
            passed=passed,
            evaluator_name="rubric",
            criterion_results=[
                CriterionResult(
                    name="criterion result",
                    score=criterion_score,
                    passed=passed,
                    weight=criterion_weight,
                    feedback=feedback,
                    metadata=metadata or {},
                )
            ],
        ),
        specs=[
            CriterionSpec(
                criterion=criterion,
                criterion_idx=0,
                max_score=1.0,
            )
        ],
    )


def test_criterion_result_entry_requires_criterion_description() -> None:
    with pytest.raises(ValidationError):
        CriterionResultEntry(
            criterion_name="criterion",
            criterion_type="test-criterion",
            score=1.0,
            passed=True,
        )


def test_criterion_result_entry_allows_nullable_optional_text_fields() -> None:
    entry = CriterionResultEntry(
        criterion_name="criterion",
        criterion_type="test-criterion",
        criterion_description="Criterion description",
        status="passed",
        score=1.0,
        passed=True,
        contribution=1.0,
        feedback=None,
        evaluation_input=None,
    )

    assert entry.feedback is None
    assert entry.evaluation_input is None


def test_build_evaluation_summary_preserves_missing_feedback_and_input() -> None:
    summary = build_evaluation_summary(
        _service_result(feedback=None),
        evaluation_input=None,
    )

    entry = summary.criterion_results[0]
    assert entry.criterion_description == "Criterion description"
    assert entry.feedback is None
    assert entry.evaluation_input is None


def test_build_evaluation_summary_includes_required_criterion_status_fields() -> None:
    summary = build_evaluation_summary(
        _service_result(
            feedback="needs supporting artifact",
            criterion_score=0.5,
            criterion_weight=2.0,
            passed=False,
            metadata={"model_reasoning": "missing supporting artifact"},
        ),
        evaluation_input="task evidence",
    )

    entry = summary.criterion_results[0]
    assert entry.status == "failed"
    assert entry.passed is False
    assert entry.weight == 2.0
    assert entry.contribution == 0.5
    assert entry.model_reasoning == "missing supporting artifact"
    assert entry.skipped_reason is None


def test_dashboard_evaluation_dto_allows_nullable_feedback_and_input() -> None:
    summary = build_evaluation_summary(
        _service_result(feedback=None),
        evaluation_input=None,
    )

    dto = build_dashboard_evaluation_dto(
        evaluation_id=uuid4(),
        run_id=uuid4(),
        task_id=uuid4(),
        total_score=1.0,
        created_at="2026-04-25T20:00:00Z",
        summary=summary,
    )

    criterion = dto.criterion_results[0]
    assert criterion.feedback is None
    assert criterion.evaluation_input is None


def test_dashboard_evaluation_dto_exposes_required_rubric_metadata() -> None:
    summary = build_evaluation_summary(
        _service_result(
            feedback="root timing marker criterion ran",
            metadata={"model_reasoning": "root completed before evaluation"},
        ),
        evaluation_input="root task evidence",
    )

    dto = build_dashboard_evaluation_dto(
        evaluation_id=uuid4(),
        run_id=uuid4(),
        task_id=uuid4(),
        total_score=1.0,
        created_at="2026-04-25T20:00:00Z",
        summary=summary,
    )

    criterion = dto.criterion_results[0]
    assert dto.evaluator_name == "rubric"
    assert dto.aggregation_rule == "weighted_sum"
    assert criterion.criterion_name == "criterion result"
    assert criterion.status == "passed"
    assert criterion.passed is True
    assert criterion.weight == 1.0
    assert criterion.contribution == 1.0
    assert criterion.model_reasoning == "root completed before evaluation"
    assert criterion.skipped_reason is None


def test_summary_migration_normalizes_missing_criterion_fields() -> None:
    migration_path = (
        Path(__file__).parents[3]
        / "ergon_core"
        / "migrations"
        / "versions"
        / "e5f6a7b8c9d0_normalize_evaluation_summary_nulls.py"
    )
    spec = util.spec_from_file_location("summary_null_migration", migration_path)
    assert spec is not None
    assert spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)

    summary = module._normalize_summary_json(
        {
            "evaluator_name": "rubric",
            "criterion_results": [
                {
                    "criterion_name": "named criterion",
                    "criterion_type": "test-criterion",
                    "score": 1.0,
                    "passed": True,
                }
            ],
        }
    )

    entry = summary["criterion_results"][0]
    assert entry["criterion_description"] == "named criterion"
    assert entry["status"] == "passed"
    assert entry["weight"] == 1.0
    assert entry["contribution"] == 1.0
    assert entry["feedback"] is None
    assert entry["model_reasoning"] is None
    assert entry["skipped_reason"] is None
    assert entry["evaluation_input"] is None
    assert entry["error"] is None
