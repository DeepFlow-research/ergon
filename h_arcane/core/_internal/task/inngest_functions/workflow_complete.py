"""Workflow completion Inngest function.

Finalizes workflow when all tasks complete.
"""

from functools import partial
from uuid import UUID

import inngest

from h_arcane.core.task import TaskStatus
from h_arcane.core._internal.db.models import Evaluation
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.events import RunCleanupEvent
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.task.events import WorkflowCompletedEvent
from h_arcane.core._internal.task.results import RunCompletionData, WorkflowCompleteResult
from h_arcane.core._internal.task.schema import parse_task_tree
from h_arcane.core._internal.utils import require_not_none, utcnow
from h_arcane.core.runner import ExecutionResult, TaskResult
from h_arcane.core.task import Resource
from h_arcane.core.dashboard import dashboard_emitter


@inngest_client.create_function(
    fn_id="workflow-complete",
    trigger=inngest.TriggerEvent(event=WorkflowCompletedEvent.name),
    retries=1,
    output_type=WorkflowCompleteResult,
)
async def workflow_complete(ctx: inngest.Context) -> WorkflowCompleteResult:
    """
    Finalize workflow when all tasks complete.

    This function:
    1. Marks Run as COMPLETED, aggregates scores, updates run (combined)
    2. Emits dashboard workflow completed event
    3. Emits cleanup event
    """
    payload = WorkflowCompletedEvent.model_validate(ctx.event.data)
    run_id = UUID(payload.run_id)

    # Finalize run: mark completed + aggregate scores + build execution result + update run
    result = await ctx.step.run(
        "finalize-run",
        partial(_finalize_run, run_id),
        output_type=WorkflowCompleteResult,
    )
    result = require_not_none(result, "finalize-run returned None")

    # Emit dashboard workflow completed event
    await ctx.step.run(
        "emit-dashboard-workflow-completed",
        partial(_emit_dashboard_workflow_completed, run_id, result.final_score),
    )

    # Emit cleanup event
    await ctx.step.run("emit-cleanup", partial(_emit_cleanup, run_id))

    return result


async def _finalize_run(run_id: UUID) -> WorkflowCompleteResult:
    """Mark completed, aggregate scores, build ExecutionResult, update run."""
    run = require_not_none(queries.runs.get(run_id), f"Run {run_id} not found")
    experiment = require_not_none(
        queries.experiments.get(run.experiment_id),
        f"Experiment {run.experiment_id} not found",
    )

    # Set completion timestamp
    completed_at = utcnow()
    started_at = run.started_at or run.created_at

    # Aggregate scores from task evaluators
    evaluators = queries.task_evaluators.get_by_run(run_id)
    completed_evaluators = [e for e in evaluators if e.status == TaskStatus.COMPLETED]

    total_score: float | None = None
    normalized_score: float | None = None
    if completed_evaluators:
        total_score = sum(e.score or 0 for e in completed_evaluators)
        max_possible = len(completed_evaluators)
        normalized_score = total_score / max_possible if max_possible > 0 else 0.0

    # Aggregate total_cost_usd from actions (last action has cumulative total)
    actions = queries.actions.get_all(run_id, order_by="action_num")
    total_cost_usd: float = 0.0
    if actions:
        # Get the max cost from any action (they're cumulative per agent)
        costs = [a.agent_total_cost_usd for a in actions if a.agent_total_cost_usd is not None]
        total_cost_usd = max(costs) if costs else 0.0

    # Build task results from executions
    executions = queries.task_executions.get_by_run(run_id)
    tree = parse_task_tree(experiment.task_tree)

    task_results: dict[UUID, TaskResult] = {}
    task_attempts: dict[UUID, int] = {}
    output_texts: list[str] = []

    for exec in executions:
        current_attempt = task_attempts.get(exec.task_id, 0)
        if exec.attempt_number > current_attempt:
            task_node = tree.find_by_id(str(exec.task_id)) if tree else None
            task_name = task_node.name if task_node else f"Task-{exec.task_id}"

            # Load task-specific outputs
            output_records = queries.resources.get_outputs_for_execution(exec.id)
            task_outputs = [Resource(name=r.name, path=r.file_path) for r in output_records]

            task_status = TaskStatus.COMPLETED if exec.status == "completed" else TaskStatus.FAILED
            task_results[exec.task_id] = TaskResult(
                task_id=exec.task_id,
                name=task_name,
                status=task_status,
                score=exec.score,
                outputs=task_outputs,
                error=exec.error_message,
            )
            task_attempts[exec.task_id] = exec.attempt_number

            # Collect output_text for aggregation
            if exec.output_text:
                output_texts.append(f"[{task_name}] {exec.output_text}")

    # Aggregate output_text from all task executions
    aggregated_output_text: str | None = None
    if output_texts:
        aggregated_output_text = "\n\n".join(output_texts)

    # Load root task output resources
    output_resources: list[Resource] = []
    if run.output_resource_ids:
        for res_id_str in run.output_resource_ids:
            try:
                db_resource = queries.resources.get(UUID(res_id_str))
                if db_resource:
                    output_resources.append(
                        Resource(name=db_resource.name, path=db_resource.file_path)
                    )
            except Exception:
                pass  # Skip invalid resource IDs

    # Build the full ExecutionResult
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
        run_id=run_id,
        experiment_id=run.experiment_id,
        error=None,
    )

    # Complete run with all data in single atomic operation
    completion_data = RunCompletionData(
        completed_at=completed_at,
        final_score=total_score,
        normalized_score=normalized_score,
        total_cost_usd=total_cost_usd,
        output_text=aggregated_output_text,
        execution_result=execution_result.model_dump(mode="json"),
    )
    queries.runs.complete(run_id, completion_data)

    # Persist run-level Evaluation record if we have evaluation data
    if completed_evaluators:
        evaluation = Evaluation(
            run_id=run_id,
            total_score=total_score or 0.0,
            max_score=float(len(completed_evaluators)),
            normalized_score=normalized_score or 0.0,
            stages_evaluated=len(completed_evaluators),
            stages_passed=sum(1 for e in completed_evaluators if (e.score or 0) > 0),
            failed_gate=None,
        )
        queries.evaluations.create_from_eval(run_id, evaluation)

    return WorkflowCompleteResult(
        run_id=run_id,
        final_score=total_score,
        normalized_score=normalized_score,
        evaluators_count=len(completed_evaluators),
    )


async def _emit_dashboard_workflow_completed(run_id: UUID, final_score: float | None) -> None:
    """Emit dashboard workflow_completed(status=completed) event."""
    run = queries.runs.get(run_id)
    if run:
        started_at = run.started_at or run.created_at
        completed_at = run.completed_at or utcnow()
        duration_seconds = (completed_at - started_at).total_seconds()

        await dashboard_emitter.workflow_completed(
            run_id=run_id,
            status="completed",
            duration_seconds=duration_seconds,
            final_score=final_score,
        )


async def _emit_cleanup(run_id: UUID) -> None:
    """Emit RunCleanupEvent (Inngest)."""
    event = RunCleanupEvent(
        run_id=str(run_id),
        status="completed",
    )
    await inngest_client.send(inngest.Event(name=RunCleanupEvent.name, data=event.model_dump()))
