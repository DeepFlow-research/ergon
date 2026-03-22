"""Workflow completion Inngest function.

Finalizes workflow when all tasks complete.
"""

from functools import partial
from uuid import UUID

import inngest

from h_arcane.core._internal.cohorts.events import emit_cohort_updated_for_run
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.events import RunCleanupEvent
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.infrastructure.tracing import (
    CompletedSpan,
    get_trace_sink,
    workflow_root_context,
    workflow_terminal_context,
)
from h_arcane.core._internal.task.events import WorkflowCompletedEvent
from h_arcane.core._internal.task.results import WorkflowCompleteResult
from h_arcane.core._internal.task.services import WorkflowFinalizationService
from h_arcane.core._internal.task.services.dto import (
    FinalizeWorkflowCommand,
    FinalizedWorkflowResult,
)
from h_arcane.core._internal.utils import require_not_none, utcnow
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
    run_id = payload.run_id
    trace_sink = get_trace_sink()
    terminal_context = workflow_terminal_context(run_id, "complete")

    async def finalize_run() -> FinalizedWorkflowResult:
        return WorkflowFinalizationService(
            trace_sink=trace_sink,
            trace_context=terminal_context,
        ).finalize(FinalizeWorkflowCommand(run_id=run_id))

    # Finalize run in the application service
    raw_result = await ctx.step.run(
        "finalize-run",
        finalize_run,
        output_type=FinalizedWorkflowResult,
    )
    result = require_not_none(raw_result, "finalize-run returned None")

    run = require_not_none(queries.runs.get(run_id), f"Run {run_id} not found after finalization")
    experiment = require_not_none(
        queries.experiments.get(run.experiment_id),
        f"Experiment {run.experiment_id} not found",
    )
    started_at = run.started_at or run.created_at
    completed_at = run.completed_at or utcnow()

    trace_sink.emit_span(
        CompletedSpan(
            name="workflow.complete",
            context=terminal_context,
            start_time=completed_at,
            end_time=completed_at,
            attributes={
                "final_score": result.final_score,
                "normalized_score": result.normalized_score,
                "evaluators_count": result.evaluators_count,
            },
        )
    )
    trace_sink.emit_span(
        CompletedSpan(
            name="workflow.execute",
            context=workflow_root_context(
                run_id,
                attributes={
                    "experiment_id": run.experiment_id,
                    "benchmark_name": str(experiment.benchmark_name),
                    "worker_model": run.worker_model,
                },
            ),
            start_time=started_at,
            end_time=completed_at,
            attributes={
                "success": True,
                "final_score": result.final_score,
                "normalized_score": result.normalized_score,
                "total_cost_usd": run.total_cost_usd,
            },
        )
    )

    # Emit dashboard workflow completed event
    await ctx.step.run(
        "emit-dashboard-workflow-completed",
        partial(_emit_dashboard_workflow_completed, run_id, result.final_score),
    )
    await ctx.step.run(
        "emit-cohort-updated",
        partial(emit_cohort_updated_for_run, run_id),
    )

    # Emit cleanup event
    await ctx.step.run("emit-cleanup", partial(_emit_cleanup, run_id))

    return WorkflowCompleteResult(
        run_id=run_id,
        final_score=result.final_score,
        normalized_score=result.normalized_score,
        evaluators_count=result.evaluators_count,
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
        run_id=run_id,
        status="completed",
    )
    await inngest_client.send(
        inngest.Event(name=RunCleanupEvent.name, data=event.model_dump(mode="json"))
    )
