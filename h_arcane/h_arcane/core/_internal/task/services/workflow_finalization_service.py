"""Application service for workflow completion and persistence."""

from __future__ import annotations

from uuid import UUID

from h_arcane.core.task import Resource, TaskStatus
from h_arcane.core._internal.db.models import Evaluation
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.tracing import TraceContext, TraceSink
from h_arcane.core._internal.task.services.dto import (
    FinalizeWorkflowCommand,
    FinalizedWorkflowResult,
    RunCompletionData,
)
from h_arcane.core._internal.utils import require_not_none, utcnow
from h_arcane.core.runner import ExecutionResult, TaskResult


class WorkflowFinalizationService:
    """Finalize workflow state and persist aggregate results."""

    def __init__(
        self,
        trace_sink: TraceSink | None = None,
        trace_context: TraceContext | None = None,
    ) -> None:
        self._trace_sink = trace_sink
        self._trace_context = trace_context

    def _add_event(self, name: str, **attributes: object) -> None:
        if self._trace_sink is None or self._trace_context is None:
            return
        self._trace_sink.add_event(self._trace_context, name, dict(attributes))

    def finalize(self, command: FinalizeWorkflowCommand) -> FinalizedWorkflowResult:
        self._add_event("workflow_finalization.started", run_id=command.run_id)
        run = require_not_none(queries.runs.get(command.run_id), f"Run {command.run_id} not found")
        experiment = require_not_none(
            queries.experiments.get(run.experiment_id),
            f"Experiment {run.experiment_id} not found",
        )

        completed_at = utcnow()
        started_at = run.started_at or run.created_at

        evaluators = queries.task_evaluators.get_by_run(command.run_id)
        completed_evaluators = [e for e in evaluators if e.status == TaskStatus.COMPLETED]

        total_score: float | None = None
        normalized_score: float | None = None
        if completed_evaluators:
            total_score = sum(e.score or 0 for e in completed_evaluators)
            max_possible = len(completed_evaluators)
            normalized_score = total_score / max_possible if max_possible > 0 else 0.0

        actions = queries.actions.get_all(command.run_id, order_by="action_num")
        total_cost_usd = 0.0
        if actions:
            costs = [a.agent_total_cost_usd for a in actions if a.agent_total_cost_usd is not None]
            total_cost_usd = max(costs) if costs else 0.0
        self._add_event("workflow_finalization.costs_computed", total_cost_usd=total_cost_usd)

        executions = queries.task_executions.get_by_run(command.run_id)
        tree = experiment.parsed_task_tree()

        task_results: dict[UUID, TaskResult] = {}
        task_attempts: dict[UUID, int] = {}
        output_texts: list[str] = []
        for execution in executions:
            current_attempt = task_attempts.get(execution.task_id, 0)
            if execution.attempt_number <= current_attempt:
                continue

            task_node = tree.find_by_id(execution.task_id) if tree else None
            task_name = task_node.name if task_node else f"Task-{execution.task_id}"
            output_records = queries.resources.get_outputs_for_execution(execution.id)
            task_outputs = [Resource(name=r.name, path=r.file_path) for r in output_records]
            task_status = (
                TaskStatus.COMPLETED
                if execution.status == TaskStatus.COMPLETED
                else TaskStatus.FAILED
            )
            task_results[execution.task_id] = TaskResult(
                task_id=execution.task_id,
                name=task_name,
                status=task_status,
                score=execution.score,
                outputs=task_outputs,
                error=execution.error_message,
            )
            task_attempts[execution.task_id] = execution.attempt_number

            if execution.output_text:
                output_texts.append(f"[{task_name}] {execution.output_text}")

        aggregated_output_text = "\n\n".join(output_texts) if output_texts else None

        output_resources: list[Resource] = []
        for resource_id in run.parsed_output_resource_ids():
            try:
                resource = queries.resources.get(resource_id)
            except Exception:
                resource = None
            if resource:
                output_resources.append(Resource(name=resource.name, path=resource.file_path))

        execution_result = ExecutionResult(
            success=True,
            status=TaskStatus.COMPLETED,
            outputs=output_resources,
            score=total_score,
            evaluation_details=run.benchmark_specific_results or {},
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=(completed_at - started_at).total_seconds(),
            total_cost_usd=total_cost_usd,
            task_results=task_results,
            run_id=command.run_id,
            experiment_id=run.experiment_id,
            error=None,
        )

        queries.runs.complete(
            command.run_id,
            RunCompletionData(
                completed_at=completed_at,
                final_score=total_score,
                normalized_score=normalized_score,
                total_cost_usd=total_cost_usd,
                output_text=aggregated_output_text,
                execution_result=execution_result.model_dump(mode="json"),
            ),
        )

        if completed_evaluators:
            queries.evaluations.create_from_eval(
                command.run_id,
                Evaluation(
                    run_id=command.run_id,
                    total_score=total_score or 0.0,
                    max_score=float(len(completed_evaluators)),
                    normalized_score=normalized_score or 0.0,
                    stages_evaluated=len(completed_evaluators),
                    stages_passed=sum(1 for e in completed_evaluators if (e.score or 0) > 0),
                    failed_gate=None,
                ),
            )
        self._add_event(
            "workflow_finalization.completed",
            final_score=total_score,
            normalized_score=normalized_score,
            evaluators_count=len(completed_evaluators),
        )

        return FinalizedWorkflowResult(
            run_id=command.run_id,
            final_score=total_score,
            normalized_score=normalized_score,
            evaluators_count=len(completed_evaluators),
        )
