"""Single front-door service for task evaluation workflow."""

from uuid import UUID

from ergon_core.api.benchmark import Task
from ergon_core.api.criterion import CriterionOutcome
from ergon_core.api.criterion.context import CriterionContext
from ergon_core.api.rubric import Evaluator, TaskEvaluationResult
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinitionEvaluator,
    ExperimentDefinitionTask,
    ExperimentDefinitionTaskEvaluator,
)
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.evaluation_summary import (
    CriterionOutcomeEntry,
    EvaluationSummary,
)
from ergon_core.core.persistence.telemetry.models import RunRecord, RunTaskExecution
from ergon_core.core.persistence.telemetry.repository import (
    CreateTaskEvaluation,
    TelemetryRepository,
)
from ergon_core.core.application.evaluation.executors import CriterionExecutor
from ergon_core.core.application.evaluation.scoring import aggregate_evaluation_scores
from ergon_core.core.application.evaluation.models import (
    CriterionSpec,
    DispatchEvaluatorsCommand,
    PreparedEvaluatorDispatch,
    PreparedSingleEvaluator,
    TaskEvaluationContext,
)
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
    """Prepare, execute, and persist task evaluations."""

    def __init__(
        self,
        criterion_executor: CriterionExecutor | None = None,
        telemetry_repo: TelemetryRepository | None = None,
    ) -> None:
        self.criterion_executor = criterion_executor
        self.telemetry_repo = telemetry_repo or TelemetryRepository()

    def prepare_dispatch(self, command: DispatchEvaluatorsCommand) -> PreparedEvaluatorDispatch:
        session = get_session()
        try:
            node = session.get(RunGraphNode, command.node_id)
            if node is None:
                raise LookupError(f"run graph node not found: {command.node_id}")
            task_id = command.task_id or node.definition_task_id
            if task_id is None:
                return PreparedEvaluatorDispatch(
                    node_id=command.node_id,
                    task_id=None,
                    evaluators_found=0,
                )
            task_evals = list(
                session.exec(
                    select(ExperimentDefinitionTaskEvaluator).where(
                        ExperimentDefinitionTaskEvaluator.experiment_definition_id
                        == command.definition_id,
                        ExperimentDefinitionTaskEvaluator.task_id == task_id,
                    )
                ).all()
            )
            if not task_evals:
                return PreparedEvaluatorDispatch(
                    node_id=command.node_id,
                    task_id=task_id,
                    evaluators_found=0,
                )
            task_row = session.get(ExperimentDefinitionTask, task_id)
            if task_row is None:
                raise LookupError(f"definition task not found: {task_id}")
            execution = session.get(RunTaskExecution, command.execution_id)
            agent_reasoning = execution.final_assistant_message if execution is not None else None
            valid_evaluators: list[PreparedSingleEvaluator] = []
            for te in task_evals:
                evaluator_def = session.exec(
                    select(ExperimentDefinitionEvaluator).where(
                        ExperimentDefinitionEvaluator.experiment_definition_id
                        == command.definition_id,
                        ExperimentDefinitionEvaluator.binding_key == te.evaluator_binding_key,
                    )
                ).first()
                if evaluator_def is None:
                    continue
                valid_evaluators.append(
                    PreparedSingleEvaluator(
                        evaluator_id=evaluator_def.id,
                        evaluator_binding_key=te.evaluator_binding_key,
                        evaluator_type=evaluator_def.evaluator_type,
                        task_input=task_row.description,
                        agent_reasoning=agent_reasoning,
                    )
                )
            return PreparedEvaluatorDispatch(
                node_id=command.node_id,
                task_id=task_id,
                evaluators_found=len(task_evals),
                valid_evaluators=valid_evaluators,
            )
        finally:
            session.close()

    async def evaluate_legacy(
        self,
        task_context: TaskEvaluationContext,
        evaluator: Evaluator,
        task: Task,
        benchmark_name: str,
    ) -> EvaluationServiceResult:
        """v1 entry point — held only for tests still exercising the
        executor-based signature.

        **Status.** Zero production callers as of PR 4. The only
        remaining caller is
        ``tests/unit/runtime/test_rubric_evaluation_service.py``,
        which specifically tests that an injected ``CriterionExecutor``
        receives the expected ``CriterionSpec``s. Production code uses
        the v2 ``evaluate`` (below).

        **Deletion gate.** PR 11 (Δ.7) deletes this method together
        with the ``CriterionExecutor`` Protocol and
        ``InngestCriterionExecutor`` — at which point the executor-spec
        test goes too. Don't add new callers.
        """

        if self.criterion_executor is None:
            raise RuntimeError("EvaluationService.evaluate_legacy requires a criterion executor")
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
        criterion_results: list[CriterionOutcome] = await self.criterion_executor.execute_all(
            task_context=task_context,
            task=task,
            benchmark_name=benchmark_name,
            criteria=specs,
        )
        return EvaluationServiceResult(
            result=evaluator.aggregate_task(task, criterion_results),
            specs=specs,
        )

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
        ``CriterionExecutor`` indirection because the Inngest retry
        boundary already lives one level up: the orchestrator
        (``execute_task._fan_out_evaluators``) gives each evaluator
        its own ``ctx.step.invoke``, so retries replay whole evaluators,
        not individual criteria.

        Sibling method ``evaluate_legacy`` keeps the v1 executor-based
        signature alive for tests that exercise it; PR 11 deletes it.
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
            self._refresh_run_evaluation_summary(session, run_id)
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
            self._refresh_run_evaluation_summary(session, run_id)
            session.commit()
        finally:
            session.close()

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
    if error is not None:
        return "errored"
    if skipped_reason is not None:
        return "skipped"
    return "passed" if passed else "failed"


def _summary_max_score(result, specs) -> float:
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
    created_at,
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
