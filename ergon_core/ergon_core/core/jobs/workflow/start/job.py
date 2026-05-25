"""Inngest function: workflow initialization and first-task dispatch."""

import logging
from datetime import UTC, datetime

from .contract import WorkflowStartedEvent, WorkflowStartResult
from ergon_core.core.jobs.task.execute.contract import TaskReadyEvent
from ergon_core.core.application.events.service import get_dashboard_event_publisher
from ergon_core.core.application.runtime.orchestration import InitializeWorkflowCommand
from ergon_core.core.application.runtime.sample_lifecycle import WorkflowService
from ergon_core.core.jobs._events import send_job_events
from ergon_core.core.infrastructure.tracing import (
    CompletedSpan,
    get_trace_sink,
    workflow_start_context,
)
from ergon_core.core.shared.utils import utcnow
from ergon_core.core.views.dashboard_events.contracts import DashboardWorkflowStartedEvent
from ergon_core.core.views.samples.service import SampleSnapshotReadService

logger = logging.getLogger(__name__)


async def run_start_workflow_job(payload: WorkflowStartedEvent) -> WorkflowStartResult:
    logger.info("workflow-start sample_id=%s definition_id=%s", payload.sample_id, payload.definition_id)
    span_start = datetime.now(UTC)

    svc = WorkflowService()
    initialized = await svc.initialize(
        InitializeWorkflowCommand(
            sample_id=payload.sample_id,
            definition_id=payload.definition_id,
        )
    )

    events = [
        (
            TaskReadyEvent.name,
            TaskReadyEvent(
                sample_id=payload.sample_id,
                definition_id=payload.definition_id,
                task_id=td.task_id,
            ).model_dump(mode="json"),
        )
        for td in initialized.initial_ready_tasks
    ]

    await send_job_events(events)

    snapshot = SampleSnapshotReadService().build_run_snapshot(payload.sample_id)
    if snapshot is None:
        raise RuntimeError(f"Run snapshot {payload.sample_id} not found after workflow start")

    await get_dashboard_event_publisher().publish(
        DashboardWorkflowStartedEvent(
            sample_id=payload.sample_id,
            definition_id=payload.definition_id,
            workflow_name=initialized.benchmark_type,
            snapshot=snapshot,
            started_at=snapshot.started_at or utcnow(),
            total_tasks=snapshot.total_tasks,
            total_leaf_tasks=snapshot.total_leaf_tasks,
        )
    )

    result = WorkflowStartResult(
        sample_id=payload.sample_id,
        initial_ready_tasks=len(initialized.initial_ready_tasks),
        total_tasks=initialized.total_tasks,
    )

    get_trace_sink().emit_span(
        CompletedSpan(
            name="workflow.start",
            context=workflow_start_context(payload.sample_id),
            start_time=span_start,
            end_time=datetime.now(UTC),
            attributes={
                "sample_id": str(payload.sample_id),
                "definition_id": str(payload.definition_id),
                "total_tasks": initialized.total_tasks,
                "initial_ready_tasks": len(initialized.initial_ready_tasks),
            },
        )
    )

    logger.info(
        "workflow-start completed: %d initial tasks of %d total",
        result.initial_ready_tasks,
        result.total_tasks,
    )
    return result
