"""Inngest function: workflow failure handling."""

import logging
from datetime import UTC, datetime

import inngest
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import RunRecord
from ergon_core.core.runtime.errors import DataIntegrityError
from ergon_core.core.runtime.events.infrastructure_events import RunCleanupEvent
from ergon_core.core.runtime.events.task_events import WorkflowFailedEvent
from ergon_core.core.runtime.inngest_client import RUN_CANCEL, inngest_client
from ergon_core.core.runtime.services.inngest_function_results import WorkflowFailedResult
from ergon_core.core.runtime.tracing import (
    CompletedSpan,
    get_trace_sink,
    truncate_text,
    workflow_failed_context,
    workflow_root_context,
)
from ergon_core.core.utils import utcnow

logger = logging.getLogger(__name__)


@inngest_client.create_function(
    fn_id="workflow-failed",
    trigger=inngest.TriggerEvent(event="workflow/failed"),
    cancel=RUN_CANCEL,
    retries=1,
    output_type=WorkflowFailedResult,
)
async def fail_workflow_fn(ctx: inngest.Context) -> WorkflowFailedResult:
    payload = WorkflowFailedEvent.model_validate(ctx.event.data)
    logger.info("workflow-failed run_id=%s error=%s", payload.run_id, payload.error)
    span_start = datetime.now(UTC)

    with get_session() as session:
        run_record = session.get(RunRecord, payload.run_id)
        if run_record is None:
            raise DataIntegrityError("RunRecord", payload.run_id)
        run_record.status = RunStatus.FAILED
        run_record.error_message = payload.error
        run_record.completed_at = utcnow()
        session.add(run_record)
        session.commit()

    await inngest_client.send(
        inngest.Event(
            name=RunCleanupEvent.name,
            data=RunCleanupEvent(
                run_id=payload.run_id,
                status="failed",
                error_message=payload.error,
            ).model_dump(mode="json"),
        )
    )

    result = WorkflowFailedResult(
        run_id=payload.run_id,
        status="failed",
        error=payload.error,
    )

    sink = get_trace_sink()
    sink.emit_span(
        CompletedSpan(
            name="workflow.failed",
            context=workflow_failed_context(payload.run_id),
            start_time=span_start,
            end_time=datetime.now(UTC),
            status_code="error",
            status_message=truncate_text(payload.error),
            attributes={
                "run_id": str(payload.run_id),
                "definition_id": str(payload.definition_id),
                "error": truncate_text(payload.error),
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
                    status_code="error",
                    status_message=truncate_text(payload.error),
                    attributes={
                        "run_id": str(payload.run_id),
                        "definition_id": str(payload.definition_id),
                        "cohort_id": str(run.cohort_id) if run.cohort_id else "",
                        "status": run.status,
                        "error": truncate_text(payload.error),
                    },
                )
            )

    return result
