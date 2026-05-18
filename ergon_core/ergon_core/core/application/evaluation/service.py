"""Single front-door service for task evaluation workflow."""

from datetime import datetime
from uuid import UUID

from ergon_core.api.benchmark import Task
from ergon_core.api.criterion.context import CriterionContext
from ergon_core.api.criterion.results import CriterionOutcome
from ergon_core.api.rubric import Evaluator, TaskEvaluationResult
from ergon_core.core.persistence.definitions.models import ExperimentDefinitionEvaluator
from ergon_core.core.persistence.shared.ids import new_id
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.evaluation_summary import (
    CriterionOutcomeEntry,
    EvaluationSummary,
)
from ergon_core.core.persistence.telemetry.models import RunRecord
from ergon_core.core.persistence.telemetry.repository import (
    CreateTaskEvaluation,
    TelemetryRepository,
)
from ergon_core.core.application.evaluation.scoring import aggregate_evaluation_scores
from ergon_core.core.application.evaluation.models import CriterionSpec
from ergon_core.core.infrastructure.inngest.errors import ContractViolationError
from ergon_core.core.application.read_models.models import (
    RunEvaluationCriterionDto,
    RunTaskEvaluationDto,
)
from pydantic import BaseModel
from sqlmodel import Session, select


class EvaluationServiceResult(BaseModel):
    """Internal result carrying both the public evaluation + spec metadata."""

    result: TaskEvaluationResult
    specs: list[CriterionSpec]


class PersistedEvaluation(BaseModel):
    """Evaluation row and dashboard DTO produced by persistence."""

    model_config = {"frozen": True}

    summary: EvaluationSummary
    dashboard_dto: RunTaskEvaluationDto


class EvaluationService:
    """Execute and persist task evaluations."""

    def __init__(
        self,
        telemetry_repo: TelemetryRepository | None = None,
    ) -> None:
        self.telemetry_repo = telemetry_repo or TelemetryRepository()

    async def evaluate(
        self,
        *,
        context: CriterionContext,
        evaluator: Evaluator,
    ) -> EvaluationServiceResult:
        """Run an evaluator against a single ``CriterionContext``.

        The v2 evaluation entry point. Iterates
        ``evaluator.criteria_for(context.task)`` and awaits
        ``criterion.evaluate(context)`` on each — there's no
        ``evaluator runner`` indirection because the Inngest retry
        boundary already lives one level up: the orchestrator
        (``execute_task._fan_out_evaluators``) gives each evaluator
        its own ``ctx.step.invoke``, so retries replay whole evaluators,
        not individual criteria.

        """

        task = context.task
        criteria = list(evaluator.criteria_for(task))
        specs = [
            CriterionSpec(
                criterion=c,
                criterion_idx=i,
                max_score=c.score_spec.max_score,
                stage_idx=0,
                stage_name="default",
                aggregation_weight=c.weight,
            )
            for i, c in enumerate(criteria)
        ]
        criterion_results: list[CriterionOutcome] = []
        for c in criteria:
            criterion_results.append(await c.evaluate(context))
        return EvaluationServiceResult(
            result=evaluator.aggregate_task(task, criterion_results),
            specs=specs,
        )

    async def persist_success(
        self,
        *,
        run_id: UUID,
        task_execution_id: UUID,
        task_id: UUID,
        binding_key: str,
        service_result: EvaluationServiceResult,
        evaluation_input: str | None = None,
    ) -> PersistedEvaluation:
        summary = build_evaluation_summary(service_result, evaluation_input=evaluation_input)
        result = service_result.result
        session = get_session()
        try:
            evaluator_id = self.lookup_evaluator_id(session, run_id, binding_key)
            evaluation = await self.telemetry_repo.create_task_evaluation(
                session,
                CreateTaskEvaluation(
                    run_id=run_id,
                    task_execution_id=task_execution_id,
                    task_id=task_id,
                    definition_evaluator_id=evaluator_id,
                    score=result.score,
                    passed=result.passed,
                    feedback=result.feedback,
                    summary_json=summary.model_dump(mode="json"),
                ),
            )
            self._refresh_run_evaluation_summary(session, run_id)
            session.commit()
            session.refresh(evaluation)
            return PersistedEvaluation(
                summary=summary,
                dashboard_dto=build_dashboard_evaluation_dto(
                    evaluation_id=evaluation.id,
                    run_id=run_id,
                    task_id=task_id,
                    total_score=result.score,
                    created_at=evaluation.created_at,
                    summary=summary,
                ),
            )
        finally:
            session.close()

    async def persist_failure(
        self,
        *,
        run_id: UUID,
        task_execution_id: UUID,
        task_id: UUID,
        binding_key: str,
        exc: Exception,
    ) -> None:
        error_type = type(exc).__name__
        summary = EvaluationSummary(
            evaluator_name=binding_key,
            max_score=0.0,
            normalized_score=0.0,
            stages_evaluated=0,
            stages_passed=0,
            criterion_results=[],
        )
        session = get_session()
        try:
            evaluator_id = self.lookup_evaluator_id(session, run_id, binding_key)
            await self.telemetry_repo.create_task_evaluation(
                session,
                CreateTaskEvaluation(
                    run_id=run_id,
                    task_execution_id=task_execution_id,
                    task_id=task_id,
                    definition_evaluator_id=evaluator_id,
                    score=0.0,
                    passed=False,
                    feedback=f"{error_type}: {exc}",
                    summary_json=summary.model_dump(mode="json"),
                ),
            )
            self._refresh_run_evaluation_summary(session, run_id)
            session.commit()
        finally:
            session.close()

    def lookup_evaluator_id(
        self,
        session: Session,
        run_id: UUID,
        binding_key: str,
        *,
        evaluator_type: str | None = None,
        snapshot_json: dict | None = None,
    ) -> UUID:
        """Resolve the ``ExperimentDefinitionEvaluator.id`` for a binding key.

        The eval body receives an id-only payload, so it executes the
        inline ``task.evaluators[i]`` object and passes only its
        ``evaluator.name``. The persistence layer needs the normalized
        evaluator id for the FK on
        ``run_task_evaluations.definition_evaluator_id``.

        The normalized evaluator row remains the persistence/read-model
        target for evaluation summaries, even though runtime dispatch
        executes the inline evaluator from ``task.evaluators``.
        """

        run = session.get(RunRecord, run_id)
        if run is None:
            raise ContractViolationError(
                f"RunRecord {run_id} not found while resolving evaluator id"
            )
        evaluator_def = session.exec(
            select(ExperimentDefinitionEvaluator).where(
                ExperimentDefinitionEvaluator.experiment_definition_id
                == run.workflow_definition_id,
                ExperimentDefinitionEvaluator.binding_key == binding_key,
            )
        ).first()
        if evaluator_def is None:
            evaluator_def = ExperimentDefinitionEvaluator(
                id=new_id(),
                experiment_definition_id=run.workflow_definition_id,
                binding_key=binding_key,
                evaluator_type=evaluator_type or binding_key,
                snapshot_json=snapshot_json or {},
            )
            session.add(evaluator_def)
            session.flush()
        return evaluator_def.id

    def _refresh_run_evaluation_summary(self, session: Session, run_id: UUID) -> None:
        run = session.get(RunRecord, run_id)
        if run is None:
            return
        evaluations = self.telemetry_repo.get_task_evaluations(session, run_id)
        score_summary = aggregate_evaluation_scores(evaluations)
        existing_summary = dict({} if run.summary_json is None else run.summary_json)
        existing_summary.update(
            {
                "final_score": score_summary.final_score,
                "normalized_score": score_summary.normalized_score,
                "evaluators_count": score_summary.evaluators_count,
            }
        )
        run.summary_json = existing_summary
        session.add(run)
        session.flush()


def _criterion_status(*, passed: bool, error: dict | None, skipped_reason: str | None) -> str:
    # TODO: inline to fix Locality of behavior violation
    # also investigate if this is even needed, seems messy.
    if error is not None:
        return "errored"
    if skipped_reason is not None:
        return "skipped"
    return "passed" if passed else "failed"


def _summary_max_score(
    result: TaskEvaluationResult,
    specs: list[CriterionSpec],
) -> float:
    # TODO: inline to fix Locality of behavior violation
    # also investigate if this is even needed, seems messy.
    if result.metadata.get("score_scale") == "normalized_0_1":
        return 1.0
    return sum(s.max_score for s in specs) if specs else 1.0


def build_evaluation_summary(
    service_result: EvaluationServiceResult,
    evaluation_input: str | None,
) -> EvaluationSummary:
    result = service_result.result
    specs = service_result.specs
    spec_by_idx = {s.criterion_idx: s for s in specs}
    max_score_total = _summary_max_score(result, specs)
    entries: list[CriterionOutcomeEntry] = []
    for i, cr in enumerate(result.criterion_results):
        spec = spec_by_idx.get(i)
        if spec is None:
            raise ContractViolationError(
                f"Criterion result at index {i} ({cr.slug!r}) has no matching "
                "CriterionSpec - specs and results are out of sync",
            )
        entries.append(
            CriterionOutcomeEntry(
                criterion_slug=cr.slug,
                criterion_name=cr.name,
                criterion_type=spec.criterion.type_slug,
                criterion_description=spec.criterion.description,
                stage_num=spec.stage_idx,
                stage_name=spec.stage_name,
                criterion_num=spec.criterion_idx,
                status=_criterion_status(
                    passed=cr.passed,
                    error=cr.error,
                    skipped_reason=cr.skipped_reason,
                ),
                score=cr.score,
                max_score=spec.max_score,
                passed=cr.passed,
                weight=cr.weight,
                contribution=cr.score,
                feedback=cr.feedback,
                model_reasoning=cr.model_reasoning,
                skipped_reason=cr.skipped_reason,
                evaluation_input=cr.evaluation_input or evaluation_input,
                evaluated_action_ids=cr.evaluated_action_ids,
                evaluated_resource_ids=cr.evaluated_resource_ids,
                observation=cr.observation,
                error=cr.error,
            )
        )
    stage_names = {s.stage_name for s in specs}
    stages_passed = sum(
        1
        for stage_name in stage_names
        if all(e.passed for e in entries if e.stage_name == stage_name)
    )
    return EvaluationSummary(
        evaluator_name=result.evaluator_name,
        max_score=max_score_total,
        normalized_score=result.score,
        stages_evaluated=len(stage_names),
        stages_passed=stages_passed,
        metadata=result.metadata,
        criterion_results=entries,
    )


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
