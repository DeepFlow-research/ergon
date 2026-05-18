"""Contracts for persisted evaluation summary nullability."""

from importlib import util
from pathlib import Path
from uuid import uuid4

import pytest
from ergon_core.api.criterion import Criterion
from ergon_core.api.criterion import (
    CriterionContext,
    CriterionEvidence,
    CriterionOutcome,
    EvidenceMessage,
)
from ergon_core.api.rubric import TaskEvaluationResult
from ergon_core.core.persistence.telemetry.evaluation_summary import CriterionOutcomeEntry
from ergon_core.core.application.evaluation.models import CriterionSpec
from ergon_core.core.application.evaluation.service import (
    build_dashboard_evaluation_dto,
    build_evaluation_summary,
)
from ergon_core.core.application.evaluation.service import EvaluationServiceResult
from pydantic import ValidationError


class _Criterion(Criterion):
    type_slug = "test-criterion"

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
        return CriterionOutcome(name=self.slug, score=1.0, passed=True)


def _service_result(
    *,
    feedback: str | None,
    criterion_score: float = 1.0,
    criterion_weight: float = 1.0,
    spec_max_score: float = 1.0,
    passed: bool = True,
    model_reasoning: str | None = None,
    skipped_reason: str | None = None,
    error: dict | None = None,
    evaluated_action_ids: list[str] | None = None,
    evaluated_resource_ids: list[str] | None = None,
    criterion_evaluation_input: str | None = None,
    criterion_description: str = "Criterion description",
    criterion_observation: CriterionEvidence | None = None,
    task_metadata: dict | None = None,
) -> EvaluationServiceResult:
    criterion = _Criterion(
        slug="criterion-slug",
        description=criterion_description,
    )
    return EvaluationServiceResult(
        result=TaskEvaluationResult(
            task_slug="task",
            score=criterion_score,
            passed=passed,
            evaluator_name="rubric",
            criterion_results=[
                CriterionOutcome(
                    name="criterion result",
                    score=criterion_score,
                    passed=passed,
                    weight=criterion_weight,
                    feedback=feedback,
                    model_reasoning=model_reasoning,
                    skipped_reason=skipped_reason,
                    error=error,
                    evaluated_action_ids=evaluated_action_ids or [],
                    evaluated_resource_ids=evaluated_resource_ids or [],
                    evaluation_input=criterion_evaluation_input,
                    observation=criterion_observation,
                )
            ],
            metadata=task_metadata or {},
        ),
        specs=[
            CriterionSpec(
                criterion=criterion,
                criterion_idx=0,
                max_score=spec_max_score,
            )
        ],
    )


def test_criterion_result_entry_requires_criterion_description() -> None:
    with pytest.raises(ValidationError):
        CriterionOutcomeEntry(
            criterion_slug="criterion",
            criterion_name="criterion",
            criterion_type="test-criterion",
            score=1.0,
            passed=True,
        )


def test_criterion_result_entry_allows_nullable_optional_text_fields() -> None:
    entry = CriterionOutcomeEntry(
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
            model_reasoning="missing supporting artifact",
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


def test_build_evaluation_summary_preserves_evaluator_normalized_score() -> None:
    summary = build_evaluation_summary(
        _service_result(
            feedback="criterion ran",
            criterion_score=0.5,
            criterion_weight=2.0,
            spec_max_score=2.0,
            passed=True,
            task_metadata={"score_scale": "normalized_0_1"},
        ),
        evaluation_input=None,
    )

    assert summary.normalized_score == 0.5
    assert summary.max_score == 1.0
    assert summary.metadata == {"score_scale": "normalized_0_1"}


def test_build_evaluation_summary_uses_full_criterion_description_field() -> None:
    summary = build_evaluation_summary(
        _service_result(
            feedback="criterion ran",
            criterion_description="The response cites official fireworks guidance.",
        ),
        evaluation_input=None,
    )

    entry = summary.criterion_results[0]
    assert entry.criterion_description == "The response cites official fireworks guidance."
    assert entry.criterion_slug == "criterion result"


def test_build_evaluation_summary_preserves_structured_observation() -> None:
    observation = CriterionEvidence(
        prompt_messages=[
            EvidenceMessage(role="system", content="Judge this rubric."),
            EvidenceMessage(role="user", content="Evidence payload."),
        ],
        evidence_resource_ids=["resource-1"],
        output={"passed": True, "reasoning": "sufficient"},
        model="openai:gpt-4o",
        details={"axis": "quality"},
    )
    summary = build_evaluation_summary(
        _service_result(
            feedback="criterion ran",
            criterion_observation=observation,
            evaluated_resource_ids=["resource-1"],
        ),
        evaluation_input=None,
    )

    entry = summary.criterion_results[0]
    assert entry.observation == observation
    assert entry.observation is not None
    assert entry.observation.prompt_messages[1].content == "Evidence payload."


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
            model_reasoning="root completed before evaluation",
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
    assert criterion.criterion_slug == "criterion result"
    assert criterion.criterion_name == "criterion result"
    assert criterion.status == "passed"
    assert criterion.passed is True
    assert criterion.weight == 1.0
    assert criterion.contribution == 1.0
    assert criterion.model_reasoning == "root completed before evaluation"
    assert criterion.skipped_reason is None


def test_build_evaluation_summary_reads_first_class_criterion_detail_fields() -> None:
    summary = build_evaluation_summary(
        _service_result(
            feedback="runtime unavailable",
            passed=False,
            error={"kind": "RuntimeError", "message": "sandbox unavailable"},
            evaluated_action_ids=["action-1"],
            evaluated_resource_ids=["resource-1"],
            criterion_evaluation_input="criterion-specific evidence",
        ),
        evaluation_input="fallback evidence",
    )

    entry = summary.criterion_results[0]
    assert entry.status == "errored"
    assert entry.error == {"kind": "RuntimeError", "message": "sandbox unavailable"}
    assert entry.evaluation_input == "criterion-specific evidence"
    assert entry.evaluated_action_ids == ["action-1"]
    assert entry.evaluated_resource_ids == ["resource-1"]


def test_summary_migration_normalizes_missing_criterion_fields() -> None:
    migration_path = (
        Path(__file__).parents[4]
        / "ergon_core"
        / "migrations"
        / "versions"
        / "e5f6a7b8c9d0_normalize_evaluation_summary_nulls.py"
    )
    if not migration_path.exists():
        pytest.skip("PR 11 reset migrations into the v2 initial schema")
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
