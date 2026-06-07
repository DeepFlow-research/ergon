"""Single front-door service for task evaluation workflow."""

from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from ergon_core.api.criterion.context import CriterionContext
from ergon_core.api.criterion.outcome import CriterionOutcome
from ergon_core.api.rubric import Evaluator, TaskEvaluationResult
from ergon_core.core.application.evaluation.models import CriterionSpec
from ergon_core.core.application.evaluation.scoring import (
    EvaluationScoreSummary,
    ScoredEvaluation,
    aggregate_evaluation_scores,
)
from ergon_core.core.application.evaluation.summary import EvaluationSummary
from ergon_core.core.infrastructure.inngest.errors import ContractViolationError
from ergon_core.core.persistence.definitions.models import ExperimentDefinitionEvaluator
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.ids import new_id
from ergon_core.core.persistence.telemetry.models import (
    SampleRecord,
    SampleTaskEvaluation,
)
from pydantic import BaseModel
from sqlmodel import Session, select

from .mappers import build_evaluation_summary


class EvaluationServiceResult(BaseModel):
    """Internal result carrying both the public evaluation + spec metadata."""

    result: TaskEvaluationResult
    specs: list[CriterionSpec]


class PersistedEvaluation(BaseModel):
    """Public fields produced after persisting one task evaluation."""

    model_config = {"frozen": True}

    summary: EvaluationSummary
    evaluation_id: UUID
    sample_id: UUID
    task_id: UUID
    total_score: float
    created_at: datetime


class EvaluationService:
    """Execute and persist task evaluations."""

    @staticmethod
    def summarize_scores(
        evaluations: Iterable[ScoredEvaluation],
    ) -> EvaluationScoreSummary:
        """Aggregate run-level evaluation scores through the evaluation facade."""

        return aggregate_evaluation_scores(evaluations)

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

        evaluator.validate_runtime_deps()
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
        sample_id: UUID,
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
            evaluator_id = self.lookup_evaluator_id(session, sample_id, binding_key)
            evaluation = await _create_task_evaluation(
                session,
                sample_id=sample_id,
                task_execution_id=task_execution_id,
                task_id=task_id,
                definition_evaluator_id=evaluator_id,
                score=result.score,
                passed=result.passed,
                feedback=result.feedback,
                summary_json=summary.model_dump(mode="json"),
            )
            self._refresh_run_evaluation_summary(session, sample_id)
            session.commit()
            session.refresh(evaluation)
            return PersistedEvaluation(
                summary=summary,
                evaluation_id=evaluation.id,
                sample_id=evaluation.sample_id,
                task_id=evaluation.task_id,
                total_score=0.0 if evaluation.score is None else evaluation.score,
                created_at=evaluation.created_at,
            )
        finally:
            session.close()

    async def persist_failure(
        self,
        *,
        sample_id: UUID,
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
            evaluator_id = self.lookup_evaluator_id(session, sample_id, binding_key)
            await _create_task_evaluation(
                session,
                sample_id=sample_id,
                task_execution_id=task_execution_id,
                task_id=task_id,
                definition_evaluator_id=evaluator_id,
                score=0.0,
                passed=False,
                feedback=f"{error_type}: {exc}",
                summary_json=summary.model_dump(mode="json"),
            )
            self._refresh_run_evaluation_summary(session, sample_id)
            session.commit()
        finally:
            session.close()

    def lookup_evaluator_id(
        self,
        session: Session,
        sample_id: UUID,
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
        ``sample_task_evaluations.definition_evaluator_id``.

        The normalized evaluator row remains the persistence/read-model
        target for evaluation summaries, even though runtime dispatch
        executes the inline evaluator from ``task.evaluators``.
        """

        run = session.get(SampleRecord, sample_id)
        if run is None:
            raise ContractViolationError(
                f"SampleRecord {sample_id} not found while resolving evaluator id"
            )
        evaluator_def = session.exec(
            select(ExperimentDefinitionEvaluator).where(
                ExperimentDefinitionEvaluator.experiment_definition_id == run.definition_id,
                ExperimentDefinitionEvaluator.binding_key == binding_key,
            )
        ).first()
        if evaluator_def is None:
            evaluator_def = ExperimentDefinitionEvaluator(
                id=new_id(),
                experiment_definition_id=run.definition_id,
                binding_key=binding_key,
                evaluator_type=evaluator_type or binding_key,
                snapshot_json=snapshot_json or {},
            )
            session.add(evaluator_def)
            session.flush()
        return evaluator_def.id

    def _refresh_run_evaluation_summary(self, session: Session, sample_id: UUID) -> None:
        run = session.get(SampleRecord, sample_id)
        if run is None:
            return
        evaluations = _list_task_evaluations(session, sample_id)
        score_summary = self.summarize_scores(evaluations)
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


def _list_task_evaluations(session: Session, sample_id: UUID) -> list[SampleTaskEvaluation]:
    stmt = select(SampleTaskEvaluation).where(SampleTaskEvaluation.sample_id == sample_id)
    return list(session.exec(stmt).all())


async def _create_task_evaluation(
    session: Session,
    *,
    sample_id: UUID,
    task_execution_id: UUID,
    task_id: UUID,
    definition_evaluator_id: UUID,
    score: float | None = None,
    passed: bool | None = None,
    feedback: str | None = None,
    summary_json: dict | None = None,
) -> SampleTaskEvaluation:
    evaluation = SampleTaskEvaluation(
        id=new_id(),
        sample_id=sample_id,
        task_execution_id=task_execution_id,
        task_id=task_id,
        definition_evaluator_id=definition_evaluator_id,
        score=score,
        passed=passed,
        feedback=feedback,
        summary_json={} if summary_json is None else summary_json,
    )
    session.add(evaluation)
    session.flush()
    return evaluation
