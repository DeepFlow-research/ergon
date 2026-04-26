"""Persistence and DTO shaping for task evaluations."""

from uuid import UUID

from ergon_core.core.api.schemas import RunEvaluationCriterionDto, RunTaskEvaluationDto
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.evaluation_summary import (
    CriterionResultEntry,
    EvaluationSummary,
)
from ergon_core.core.persistence.telemetry.repositories import (
    CreateTaskEvaluation,
    TelemetryRepository,
)
from ergon_core.core.runtime.errors import ContractViolationError
from ergon_core.core.runtime.services.rubric_evaluation_service import EvaluationServiceResult
from pydantic import BaseModel


class PersistedEvaluation(BaseModel):
    """Evaluation row and dashboard DTO produced by persistence."""

    model_config = {"frozen": True}

    summary: EvaluationSummary
    dashboard_dto: RunTaskEvaluationDto


class EvaluationPersistenceService:
    """Persist task evaluations and produce typed dashboard DTOs."""

    def __init__(self, telemetry_repo: TelemetryRepository | None = None) -> None:
        self.telemetry_repo = telemetry_repo or TelemetryRepository()

    def persist_success(
        self,
        *,
        run_id: UUID,
        node_id: UUID,
        task_execution_id: UUID,
        definition_task_id: UUID | None,
        evaluator_id: UUID,
        service_result: EvaluationServiceResult,
        evaluation_input: str | None = None,
    ) -> PersistedEvaluation:
        summary = build_evaluation_summary(service_result, evaluation_input=evaluation_input)
        result = service_result.result
        session = get_session()
        try:
            evaluation = self.telemetry_repo.create_task_evaluation(
                session,
                CreateTaskEvaluation(
                    run_id=run_id,
                    node_id=node_id,
                    task_execution_id=task_execution_id,
                    definition_task_id=definition_task_id,
                    definition_evaluator_id=evaluator_id,
                    score=result.score,
                    passed=result.passed,
                    feedback=result.feedback,
                    summary_json=summary.model_dump(mode="json"),
                ),
            )
            self.telemetry_repo.refresh_run_evaluation_summary(session, run_id)
            session.commit()
            session.refresh(evaluation)
            return PersistedEvaluation(
                summary=summary,
                dashboard_dto=build_dashboard_evaluation_dto(
                    evaluation_id=evaluation.id,
                    run_id=run_id,
                    task_id=node_id,
                    total_score=result.score,
                    created_at=evaluation.created_at,
                    summary=summary,
                ),
            )
        finally:
            session.close()

    def persist_failure(
        self,
        *,
        run_id: UUID,
        node_id: UUID,
        task_execution_id: UUID,
        definition_task_id: UUID | None,
        evaluator_id: UUID,
        evaluator_name: str,
        exc: Exception,
    ) -> None:
        error_type = type(exc).__name__
        summary = EvaluationSummary(
            evaluator_name=evaluator_name,
            max_score=0.0,
            normalized_score=0.0,
            stages_evaluated=0,
            stages_passed=0,
            criterion_results=[],
        )
        session = get_session()
        try:
            self.telemetry_repo.create_task_evaluation(
                session,
                CreateTaskEvaluation(
                    run_id=run_id,
                    node_id=node_id,
                    task_execution_id=task_execution_id,
                    definition_task_id=definition_task_id,
                    definition_evaluator_id=evaluator_id,
                    score=0.0,
                    passed=False,
                    feedback=f"{error_type}: {exc}",
                    summary_json=summary.model_dump(mode="json"),
                ),
            )
            self.telemetry_repo.refresh_run_evaluation_summary(session, run_id)
            session.commit()
        finally:
            session.close()


def build_evaluation_summary(
    service_result: EvaluationServiceResult,
    evaluation_input: str | None,
) -> EvaluationSummary:
    """Build a strongly typed evaluation summary from service result + specs."""
    result = service_result.result
    specs = service_result.specs

    spec_by_idx = {s.criterion_idx: s for s in specs}
    max_score_total = sum(s.max_score for s in specs) if specs else 1.0

    entries: list[CriterionResultEntry] = []
    for i, cr in enumerate(result.criterion_results):
        spec = spec_by_idx.get(i)
        if spec is None:
            raise ContractViolationError(
                f"Criterion result at index {i} ({cr.name!r}) has no matching "
                f"CriterionSpec - specs and results are out of sync",
            )
        entries.append(
            CriterionResultEntry(
                criterion_name=cr.name,
                criterion_type=spec.criterion.type_slug,
                criterion_description=spec.criterion.name,
                stage_num=spec.stage_idx,
                stage_name=spec.stage_name,
                criterion_num=spec.criterion_idx,
                score=cr.score,
                max_score=spec.max_score,
                passed=cr.passed,
                weight=cr.weight,
                feedback=cr.feedback,
                evaluation_input=evaluation_input,
            )
        )

    total_score = result.score
    normalized = total_score / max_score_total if max_score_total > 0 else 0.0

    stage_names = {s.stage_name for s in specs}
    stages_passed = sum(
        1
        for stage_name in stage_names
        if all(e.passed for e in entries if e.stage_name == stage_name)
    )

    return EvaluationSummary(
        evaluator_name=result.evaluator_name,
        max_score=max_score_total,
        normalized_score=normalized,
        stages_evaluated=len(stage_names),
        stages_passed=stages_passed,
        criterion_results=entries,
    )


def build_dashboard_evaluation_dto(
    *,
    evaluation_id: UUID,
    run_id: UUID,
    task_id: UUID,
    total_score: float,
    created_at,
    summary: EvaluationSummary,
) -> RunTaskEvaluationDto:
    criterion_results = [
        RunEvaluationCriterionDto(
            id=f"{evaluation_id}-{i}",
            stage_num=cr.stage_num,
            stage_name=cr.stage_name,
            criterion_num=cr.criterion_num,
            criterion_type=cr.criterion_type,
            criterion_description=cr.criterion_description,
            evaluation_input=cr.evaluation_input,
            score=cr.score,
            max_score=cr.max_score,
            feedback=cr.feedback,
            evaluated_action_ids=cr.evaluated_action_ids,
            evaluated_resource_ids=cr.evaluated_resource_ids,
            error=cr.error,
        )
        for i, cr in enumerate(summary.criterion_results)
    ]
    return RunTaskEvaluationDto(
        id=str(evaluation_id),
        run_id=str(run_id),
        task_id=str(task_id),
        total_score=total_score,
        max_score=summary.max_score,
        normalized_score=summary.normalized_score,
        stages_evaluated=summary.stages_evaluated,
        stages_passed=summary.stages_passed,
        failed_gate=summary.failed_gate,
        created_at=created_at,
        criterion_results=criterion_results,
    )
