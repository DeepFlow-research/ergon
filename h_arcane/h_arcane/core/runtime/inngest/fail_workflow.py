"""Inngest function: workflow failure handling."""

import logging

import inngest
from h_arcane.core.persistence.shared.db import get_session
from h_arcane.core.persistence.shared.enums import RunStatus
from h_arcane.core.persistence.telemetry.models import RunRecord
from h_arcane.core.runtime.events.infrastructure_events import RunCleanupEvent
from h_arcane.core.runtime.events.task_events import WorkflowFailedEvent
from h_arcane.core.runtime.inngest_client import RUN_CANCEL, inngest_client
from h_arcane.core.runtime.errors import DataIntegrityError
from h_arcane.core.runtime.services.inngest_function_results import WorkflowFailedResult
from h_arcane.core.utils import utcnow

logger = logging.getLogger(__name__)


@inngest_client.create_function(
    fn_id="workflow-failed",
    trigger=inngest.TriggerEvent(event="workflow/failed"),
    cancel=RUN_CANCEL,
    retries=1,
    output_type=WorkflowFailedResult,
)
async def fail_workflow_fn(ctx: inngest.Context) -> WorkflowFailedResult:
    payload = WorkflowFailedEvent(**ctx.event.data)
    logger.info("workflow-failed run_id=%s error=%s", payload.run_id, payload.error)

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
    return result
