"""Workflow failure Inngest function.

Handles workflow failure.
"""

from datetime import datetime, timezone
from uuid import UUID

import inngest

from h_arcane.core._internal.db.models import RunStatus
from h_arcane.core.task import TaskStatus
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.events import RunCleanupEvent
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.task.events import WorkflowFailedEvent
from h_arcane.core._internal.task.results import WorkflowFailedResult
from h_arcane.core.runner import ExecutionResult


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
    """
    payload = WorkflowFailedEvent.model_validate(ctx.event.data)
    run_id = UUID(payload.run_id)
    error_msg = payload.error

    # Combined: mark failed + build execution result + emit cleanup
    async def fail_and_cleanup() -> None:
        run = queries.runs.get(run_id)
        if not run:
            # Emit cleanup anyway
            event = RunCleanupEvent(
                run_id=str(run_id),
                status="failed",
                error_message=error_msg,
            )
            await inngest_client.send(
                inngest.Event(name=RunCleanupEvent.name, data=event.model_dump())
            )
            return

        # Set completion timestamp
        completed_at = datetime.now(timezone.utc)
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
            run_id=str(run_id),
            status="failed",
            error_message=error_msg,
        )
        await inngest_client.send(inngest.Event(name=RunCleanupEvent.name, data=event.model_dump()))

    await ctx.step.run("fail-and-cleanup", fail_and_cleanup)

    return WorkflowFailedResult(
        run_id=run_id,
        error=error_msg,
    )
