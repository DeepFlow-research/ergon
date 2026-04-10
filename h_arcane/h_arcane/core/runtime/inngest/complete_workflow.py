"""Inngest function: workflow completion finalization."""

import logging
from datetime import UTC, datetime

import inngest
from h_arcane.core.persistence.shared.db import get_session
from h_arcane.core.persistence.telemetry.models import RunRecord
from h_arcane.core.runtime.events.infrastructure_events import RunCleanupEvent
from h_arcane.core.runtime.events.task_events import WorkflowCompletedEvent
from h_arcane.core.runtime.inngest_client import RUN_CANCEL, inngest_client
from h_arcane.core.runtime.services.inngest_function_results import WorkflowCompleteResult
from h_arcane.core.runtime.services.orchestration_dto import FinalizeWorkflowCommand
from h_arcane.core.runtime.services.workflow_finalization_service import (
    WorkflowFinalizationService,
)
from h_arcane.core.runtime.tracing import (
    CompletedSpan,
    get_trace_sink,
    workflow_complete_context,
    workflow_root_context,
)
from h_arcane.core.dashboard import emit_cohort_updated_for_run

logger = logging.getLogger(__name__)


@inngest_client.create_function(
    fn_id="workflow-complete",
    trigger=inngest.TriggerEvent(event="workflow/completed"),
    cancel=RUN_CANCEL,
    retries=1,
    output_type=WorkflowCompleteResult,
)
async def complete_workflow_fn(ctx: inngest.Context) -> WorkflowCompleteResult:
    payload = WorkflowCompletedEvent.model_validate(ctx.event.data)
    logger.info("workflow-complete run_id=%s", payload.run_id)
    span_start = datetime.now(UTC)

    svc = WorkflowFinalizationService()
    finalized = svc.finalize(
        FinalizeWorkflowCommand(
            run_id=payload.run_id,
            definition_id=payload.definition_id,
        )
    )

    await emit_cohort_updated_for_run(payload.run_id)

    await inngest_client.send(
        inngest.Event(
            name=RunCleanupEvent.name,
            data=RunCleanupEvent(
                run_id=payload.run_id,
                status="completed",
            ).model_dump(mode="json"),
        )
    )

    result = WorkflowCompleteResult(
        run_id=payload.run_id,
        status="completed",
        final_score=finalized.final_score,
        normalized_score=finalized.normalized_score,
        evaluators_count=finalized.evaluators_count,
    )

    sink = get_trace_sink()
    sink.emit_span(
        CompletedSpan(
            name="workflow.complete",
            context=workflow_complete_context(payload.run_id),
            start_time=span_start,
            end_time=datetime.now(UTC),
            attributes={
                "run_id": str(payload.run_id),
                "definition_id": str(payload.definition_id),
                "final_score": finalized.final_score,
                "normalized_score": finalized.normalized_score,
                "evaluators_count": finalized.evaluators_count,
            },
        )
    )

    with get_session() as session:
        run = session.get(RunRecord, payload.run_id)
        if run and run.started_at and run.completed_at:
            sink.emit_span(
                CompletedSpan(
                    name="workflow.execute",
                    context=workflow_root_context(payload.run_id),
                    start_time=run.started_at,
                    end_time=run.completed_at,
                    attributes={
                        "run_id": str(payload.run_id),
                        "definition_id": str(payload.definition_id),
                        "cohort_id": str(run.cohort_id) if run.cohort_id else "",
                        "status": run.status,
                        "final_score": finalized.final_score,
                        "normalized_score": finalized.normalized_score,
                    },
                )
            )

    logger.info(
        "workflow-complete done: score=%s normalized=%s evaluators=%d",
        result.final_score,
        result.normalized_score,
        result.evaluators_count,
    )
    return result
