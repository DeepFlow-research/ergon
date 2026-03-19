"""Workflow failure Inngest function.

Handles workflow failure.
"""

from functools import partial
from uuid import UUID

import inngest

from h_arcane.core._internal.db.models import RunStatus
from h_arcane.core.task import TaskStatus
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.events import RunCleanupEvent
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.infrastructure.tracing import (
    CompletedSpan,
    get_trace_sink,
    workflow_root_context,
    workflow_terminal_context,
)
from h_arcane.core._internal.task.events import WorkflowFailedEvent
from h_arcane.core._internal.task.results import WorkflowFailedResult
from h_arcane.core._internal.utils import utcnow
from h_arcane.core.runner import ExecutionResult
from h_arcane.core.dashboard import dashboard_emitter


@inngest_client.create_function(
    fn_id="workflow-failed",
    trigger=inngest.TriggerEvent(event=WorkflowFailedEvent.name),
    retries=0,
    output_type=WorkflowFailedResult,
)
async def workflow_failed(ctx: inngest.Context) -> WorkflowFailedResult:
    """
    Handle workflow failure.

    This function:
    1. Marks Run as FAILED and records error message
    2. Emits cleanup event
    3. Emits dashboard workflow failed event
    """
    payload = WorkflowFailedEvent.model_validate(ctx.event.data)
    run_id = payload.run_id
    error_msg = payload.error
    trace_sink = get_trace_sink()

    # Mark failed + build execution result + emit cleanup
    await ctx.step.run(
        "fail-and-cleanup",
        partial(_fail_and_cleanup, run_id, error_msg),
    )

    # Emit dashboard workflow completed (failed) event
    await ctx.step.run(
        "emit-dashboard-workflow-failed",
        partial(_emit_dashboard_workflow_failed, run_id, error_msg),
    )

    run = queries.runs.get(run_id)
    if run:
        completed_at = run.completed_at or utcnow()
        started_at = run.started_at or run.created_at
        trace_sink.emit_span(
            CompletedSpan(
                name="workflow.failed",
                context=workflow_terminal_context(run_id, "failed"),
                start_time=completed_at,
                end_time=completed_at,
                attributes={"error": error_msg},
                status_code="error",
                status_message=error_msg,
            )
        )
        trace_sink.emit_span(
            CompletedSpan(
                name="workflow.execute",
                context=workflow_root_context(
                    run_id,
                    attributes={"experiment_id": run.experiment_id},
                ),
                start_time=started_at,
                end_time=completed_at,
                attributes={
                    "success": False,
                    "error": error_msg,
                    "worker_model": run.worker_model,
                    "total_cost_usd": run.total_cost_usd,
                },
                status_code="error",
                status_message=error_msg,
            )
        )

    return WorkflowFailedResult(
        run_id=run_id,
        error=error_msg,
    )


async def _fail_and_cleanup(run_id: UUID, error_msg: str) -> None:
    """Mark run failed, build ExecutionResult, emit RunCleanupEvent (Inngest)."""
    run = queries.runs.get(run_id)
    if not run:
        # Emit cleanup anyway
        event = RunCleanupEvent(
            run_id=run_id,
            status="failed",
            error_message=error_msg,
        )
        await inngest_client.send(inngest.Event(name=RunCleanupEvent.name, data=event.model_dump()))
        return

    # Set completion timestamp
    completed_at = utcnow()
    started_at = run.started_at or run.created_at

    # Build the failed ExecutionResult
    execution_result = ExecutionResult(
        success=False,
        status=TaskStatus.FAILED,
        outputs=[],
        score=None,
        evaluation_details={},
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=(completed_at - started_at).total_seconds(),
        total_cost_usd=run.total_cost_usd or 0.0,
        task_results={},
        run_id=run_id,
        experiment_id=run.experiment_id,
        error=error_msg,
    )

    # Update run
    run.status = RunStatus.FAILED
    run.error_message = error_msg
    run.completed_at = completed_at
    run.execution_result = execution_result.model_dump(mode="json")
    queries.runs.update(run)

    # Emit cleanup event
    event = RunCleanupEvent(
        run_id=run_id,
        status="failed",
        error_message=error_msg,
    )
    await inngest_client.send(inngest.Event(name=RunCleanupEvent.name, data=event.model_dump()))


async def _emit_dashboard_workflow_failed(run_id: UUID, error_msg: str) -> None:
    """Emit dashboard workflow_completed(status=failed) event."""
    run = queries.runs.get(run_id)
    if run:
        started_at = run.started_at or run.created_at
        completed_at = run.completed_at or utcnow()
        duration_seconds = (completed_at - started_at).total_seconds()

        await dashboard_emitter.workflow_completed(
            run_id=run_id,
            status="failed",
            duration_seconds=duration_seconds,
            final_score=None,
            error=error_msg,
        )
