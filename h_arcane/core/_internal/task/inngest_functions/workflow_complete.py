"""Workflow completion Inngest function.

Finalizes workflow when all tasks complete.
"""

from datetime import datetime, timezone
from uuid import UUID

import inngest

from h_arcane.core._internal.db.models import RunStatus, TaskStatus
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.events import RunCleanupEvent
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.task.events import WorkflowCompletedEvent
from h_arcane.core._internal.task.results import WorkflowCompleteResult
from h_arcane.core._internal.utils import require_not_none


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
    2. Emits cleanup event
    """
    payload = WorkflowCompletedEvent.model_validate(ctx.event.data)
    run_id = UUID(payload.run_id)

    # Combined: mark completed + aggregate scores + update run
    async def finalize_run() -> WorkflowCompleteResult:
        # Mark run as completed
        run = queries.runs.get(run_id)
        if run:
            run.status = RunStatus.COMPLETED
            run.completed_at = datetime.now(timezone.utc)
            queries.runs.update(run)

        # Aggregate scores from task evaluators
        evaluators = queries.task_evaluators.get_by_run(run_id)
        completed_evaluators = [e for e in evaluators if e.status == TaskStatus.COMPLETED]

        if not completed_evaluators:
            return WorkflowCompleteResult(
                run_id=run_id,
                final_score=None,
                normalized_score=None,
                evaluators_count=0,
            )

        total_score = sum(e.score or 0 for e in completed_evaluators)
        max_possible = len(completed_evaluators)  # Assuming max 1.0 per evaluator
        normalized_score = total_score / max_possible if max_possible > 0 else 0.0

        # Update run with scores
        run = queries.runs.get(run_id)
        if run:
            run.final_score = total_score
            run.normalized_score = normalized_score
            queries.runs.update(run)

        return WorkflowCompleteResult(
            run_id=run_id,
            final_score=total_score,
            normalized_score=normalized_score,
            evaluators_count=len(completed_evaluators),
        )

    result = await ctx.step.run("finalize-run", finalize_run, output_type=WorkflowCompleteResult)
    result = require_not_none(result, "finalize-run returned None")

    # Emit cleanup event
    async def emit_cleanup() -> None:
        event = RunCleanupEvent(
            run_id=str(run_id),
            status="completed",
        )
        await inngest_client.send(inngest.Event(name=RunCleanupEvent.name, data=event.model_dump()))

    await ctx.step.run("emit-cleanup", emit_cleanup)

    return result
