"""Single front-door service for task evaluation workflow."""

from uuid import UUID

from ergon_core.api.benchmark import Task
from ergon_core.api.criterion import CriterionOutcome
from ergon_core.api.rubric import Evaluator, TaskEvaluationResult
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.evaluation_summary import (
    CriterionOutcomeEntry,
    EvaluationSummary,
)
from ergon_core.core.persistence.telemetry.models import RunRecord, RunTaskExecution
from ergon_core.core.persistence.telemetry.repositories import (
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
            node = session.exec(
                select(RunGraphNode).where(
                    RunGraphNode.run_id == command.run_id,
                    RunGraphNode.task_id == command.task_id,
                )
            ).first()
            if node is None:
                raise LookupError(f"run graph node not found: {command.task_id}")
            task = Task.from_definition(node.task_json, task_id=node.task_id)
            execution = session.get(RunTaskExecution, command.execution_id)
            agent_reasoning = execution.final_assistant_message if execution is not None else None
            valid_evaluators = [
                PreparedSingleEvaluator(
                    evaluator_index=index,
                    evaluator_name=evaluator.name,
                    task_input=task.description,
                    agent_reasoning=agent_reasoning,
                )
                for index, evaluator in enumerate(task.evaluators)
            ]
            return PreparedEvaluatorDispatch(
                node_id=node.id,
                task_id=node.task_id,
                evaluators_found=len(task.evaluators),
                valid_evaluators=valid_evaluators,
            )
        finally:
            session.close()

    async def evaluate(
        self,
        task_context: TaskEvaluationContext,
        evaluator: Evaluator,
        task: Task,
        benchmark_name: str,
    ) -> EvaluationServiceResult:
        if self.criterion_executor is None:
            raise RuntimeError("EvaluationService.evaluate requires a criterion executor")
        specs = _criterion_specs(evaluator, task)
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

    def persist_success(
        self,
        *,
        run_id: UUID,
        node_id: UUID,
        task_execution_id: UUID,
        definition_task_id: UUID | None,
        evaluator_index: int,
        evaluator_name: str,
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
                    evaluator_index=evaluator_index,
                    evaluator_name=evaluator_name,
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
        evaluator_index: int,
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
                    evaluator_index=evaluator_index,
                    evaluator_name=evaluator_name,
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


def _criterion_specs(evaluator: Evaluator, task: Task) -> list[CriterionSpec]:
    weighted_criteria = getattr(evaluator, "criteria", None)
    if weighted_criteria is not None:
        return [
            CriterionSpec(
                criterion=weighted.criterion,
                criterion_idx=i,
                max_score=weighted.criterion.score_spec.max_score,
                stage_idx=0,
                stage_name="default",
                aggregation_weight=weighted.weight,
            )
            for i, weighted in enumerate(weighted_criteria)
        ]

    return [
        CriterionSpec(
            criterion=criterion,
            criterion_idx=i,
            max_score=criterion.score_spec.max_score,
            stage_idx=0,
            stage_name="default",
            aggregation_weight=criterion.weight,
        )
        for i, criterion in enumerate(evaluator.criteria_for(task))
    ]


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
