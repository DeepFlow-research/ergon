"""Inngest function: workflow failure handling."""

import logging
from datetime import UTC, datetime

from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.samples.models import SampleStatusEventRow
from ergon_core.core.persistence.shared.enums import SampleStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord
from ergon_core.core.application.samples.events import SampleRuntimeEventAppender
from ergon_core.core.infrastructure.inngest.errors import DataIntegrityError
from ergon_core.core.jobs.run.cleanup.contract import SampleCleanupEvent
from .contract import WorkflowFailedEvent, WorkflowFailedResult
from ergon_core.core.jobs._events import send_job_event
from ergon_core.core.infrastructure.tracing import (
    CompletedSpan,
    get_trace_sink,
    truncate_text,
    workflow_failed_context,
    workflow_root_context,
)
from ergon_core.core.shared.utils import utcnow

logger = logging.getLogger(__name__)


async def run_fail_workflow_job(payload: WorkflowFailedEvent) -> WorkflowFailedResult:
    logger.info("workflow-failed sample_id=%s error=%s", payload.sample_id, payload.error)
    span_start = datetime.now(UTC)

    with get_session() as session:
        run_record = session.get(SampleRecord, payload.sample_id)
        if run_record is None:
            raise DataIntegrityError("SampleRecord", payload.sample_id)
        run_record.status = SampleStatus.FAILED
        run_record.error_message = payload.error
        run_record.completed_at = utcnow()
        session.add(run_record)
        SampleRuntimeEventAppender(session).append_status_event(
            SampleStatusEventRow(
                sample_id=payload.sample_id,
                event_type="sample.status_changed",
                status=SampleStatus.FAILED,
                actor="system:workflow_failed",
                event_timestamp=run_record.completed_at,
                payload_json={"error": payload.error},
            )
        )
        session.commit()

    await send_job_event(
        SampleCleanupEvent.name,
        SampleCleanupEvent(
            sample_id=payload.sample_id,
            status="failed",
            error_message=payload.error,
        ).model_dump(mode="json"),
    )

    result = WorkflowFailedResult(
        sample_id=payload.sample_id,
        status="failed",
        error=payload.error,
    )

    sink = get_trace_sink()
    sink.emit_span(
        CompletedSpan(
            name="workflow.failed",
            context=workflow_failed_context(payload.sample_id),
            start_time=span_start,
            end_time=datetime.now(UTC),
            status_code="error",
            status_message=truncate_text(payload.error),
            attributes={
                "sample_id": str(payload.sample_id),
                "definition_id": str(payload.definition_id),
                "error": truncate_text(payload.error),
            },
        )
    )

    with get_session() as session:
        run = session.get(SampleRecord, payload.sample_id)
        if run and run.started_at and run.completed_at:
            sink.emit_span(
                CompletedSpan(
                    name="workflow.execute",
                    context=workflow_root_context(payload.sample_id),
                    start_time=run.started_at,
                    end_time=run.completed_at,
                    status_code="error",
                    status_message=truncate_text(payload.error),
                    attributes={
                        "sample_id": str(payload.sample_id),
                        "definition_id": str(payload.definition_id),
                        "status": run.status,
                        "error": truncate_text(payload.error),
                    },
                )
            )

    return result
