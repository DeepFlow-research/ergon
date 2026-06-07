"""Inngest function: workflow completion finalization."""

import logging
from datetime import UTC, datetime

from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import SampleRecord
from ergon_core.core.jobs.run.cleanup.contract import SampleCleanupEvent
from .contract import WorkflowCompletedEvent, WorkflowCompleteResult
from ergon_core.core.application.events.service import get_dashboard_event_publisher
from ergon_core.core.application.runtime.orchestration import FinalizeWorkflowCommand
from ergon_core.core.application.runtime.sample_lifecycle import WorkflowService
from ergon_core.core.jobs._events import send_job_event
from ergon_core.core.infrastructure.tracing import (
    CompletedSpan,
    get_trace_sink,
    workflow_complete_context,
    workflow_root_context,
)
from ergon_core.core.shared.utils import utcnow
from ergon_core.core.views.dashboard_events.contracts import DashboardWorkflowCompletedEvent

logger = logging.getLogger(__name__)


async def run_complete_workflow_job(payload: WorkflowCompletedEvent) -> WorkflowCompleteResult:
    logger.info("workflow-complete sample_id=%s", payload.sample_id)
    span_start = datetime.now(UTC)

    svc = WorkflowService()
    finalized = svc.finalize(
        FinalizeWorkflowCommand(
            sample_id=payload.sample_id,
            definition_id=payload.definition_id,
        )
    )

    with get_session() as _session:
        _run = _session.get(SampleRecord, payload.sample_id)
        _duration = (
            (_run.completed_at - _run.started_at).total_seconds()
            if _run and _run.started_at and _run.completed_at
            else 0.0
        )
    await get_dashboard_event_publisher().publish(
        DashboardWorkflowCompletedEvent(
            sample_id=payload.sample_id,
            status="completed",
            completed_at=utcnow(),
            duration_seconds=_duration,
            final_score=finalized.final_score,
        )
    )

    await send_job_event(
        SampleCleanupEvent.name,
        SampleCleanupEvent(
            sample_id=payload.sample_id,
            status="completed",
        ).model_dump(mode="json"),
    )

    result = WorkflowCompleteResult(
        sample_id=payload.sample_id,
        status="completed",
        final_score=finalized.final_score,
        normalized_score=finalized.normalized_score,
        evaluators_count=finalized.evaluators_count,
    )

    sink = get_trace_sink()
    sink.emit_span(
        CompletedSpan(
            name="workflow.complete",
            context=workflow_complete_context(payload.sample_id),
            start_time=span_start,
            end_time=datetime.now(UTC),
            attributes={
                "sample_id": str(payload.sample_id),
                "definition_id": str(payload.definition_id),
                "final_score": finalized.final_score,
                "normalized_score": finalized.normalized_score,
                "evaluators_count": finalized.evaluators_count,
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
                    attributes={
                        "sample_id": str(payload.sample_id),
                        "definition_id": str(payload.definition_id),
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
