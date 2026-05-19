"""Mapping helpers for persisted evaluation rows."""

from datetime import datetime
from uuid import UUID

from ergon_core.core.application.evaluation.summary import EvaluationSummary
from ergon_core.core.application.read_models.models import (
    RunEvaluationCriterionDto,
    RunTaskEvaluationDto,
)
from ergon_core.core.persistence.telemetry.models import RunTaskEvaluation


def build_dashboard_evaluation_dto(
    *,
    evaluation_id: UUID,
    run_id: UUID,
    task_id: UUID,
    total_score: float,
    created_at: datetime,
    summary: EvaluationSummary,
) -> RunTaskEvaluationDto:
    criterion_results = [
        RunEvaluationCriterionDto(
            id=f"{evaluation_id}-{i}",
            stage_num=cr.stage_num,
            stage_name=cr.stage_name,
            criterion_num=cr.criterion_num,
            criterion_slug=cr.criterion_slug,
            criterion_type=cr.criterion_type,
            criterion_description=cr.criterion_description,
            criterion_name=cr.criterion_name,
            status=cr.status,
            passed=cr.passed,
            weight=cr.weight,
            contribution=cr.contribution,
            evaluation_input=cr.evaluation_input,
            score=cr.score,
            max_score=cr.max_score,
            feedback=cr.feedback,
            model_reasoning=cr.model_reasoning,
            skipped_reason=cr.skipped_reason,
            evaluated_action_ids=cr.evaluated_action_ids,
            evaluated_resource_ids=cr.evaluated_resource_ids,
            observation=cr.observation.model_dump(mode="json") if cr.observation else None,
            error=cr.error,
        )
        for i, cr in enumerate(summary.criterion_results)
    ]
    return RunTaskEvaluationDto(
        id=str(evaluation_id),
        run_id=str(run_id),
        task_id=str(task_id),
        evaluator_name=summary.evaluator_name,
        aggregation_rule="weighted_sum",
        total_score=total_score,
        max_score=summary.max_score,
        normalized_score=summary.normalized_score,
        stages_evaluated=summary.stages_evaluated,
        stages_passed=summary.stages_passed,
        failed_gate=summary.failed_gate,
        created_at=created_at,
        criterion_results=criterion_results,
    )


def evaluation_row_to_dto(evaluation: RunTaskEvaluation) -> RunTaskEvaluationDto:
    summary = EvaluationSummary.model_validate(evaluation.summary_json)
    return build_dashboard_evaluation_dto(
        evaluation_id=evaluation.id,
        run_id=evaluation.run_id,
        task_id=evaluation.task_id,
        total_score=0.0 if evaluation.score is None else evaluation.score,
        created_at=evaluation.created_at,
        summary=summary,
    )
