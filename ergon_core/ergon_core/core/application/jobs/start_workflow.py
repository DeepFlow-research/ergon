"""Inngest function: workflow initialization and first-task dispatch."""

import logging
from datetime import UTC, datetime

from ergon_core.core.application.events.task_events import (
    TaskReadyEvent,
    WorkflowStartedEvent,
)
from ergon_core.core.infrastructure.inngest.client import InngestEvent, inngest_client
from ergon_core.core.application.jobs.models import WorkflowStartResult
from ergon_core.core.application.ports.dashboard import get_dashboard_event_publisher
from ergon_core.core.application.workflows.orchestration import InitializeWorkflowCommand
from ergon_core.core.application.workflows.service import WorkflowService
from ergon_core.core.infrastructure.tracing import (
    CompletedSpan,
    get_trace_sink,
    workflow_start_context,
)
from ergon_core.core.shared.utils import utcnow
from ergon_core.core.views.dashboard_events.contracts import DashboardWorkflowStartedEvent
from ergon_core.core.views.runs.service import RunReadService

logger = logging.getLogger(__name__)


async def run_start_workflow_job(payload: WorkflowStartedEvent) -> WorkflowStartResult:
    logger.info("workflow-start run_id=%s definition_id=%s", payload.run_id, payload.definition_id)
    span_start = datetime.now(UTC)

    svc = WorkflowService()
    initialized = await svc.initialize(
        InitializeWorkflowCommand(
            run_id=payload.run_id,
            definition_id=payload.definition_id,
        )
    )

    events = [
        InngestEvent(
            name=TaskReadyEvent.name,
            data=TaskReadyEvent(
                run_id=payload.run_id,
                definition_id=payload.definition_id,
                task_id=td.task_id,
            ).model_dump(mode="json"),
        )
        for td in initialized.initial_ready_tasks
    ]

    if events:
        await inngest_client.send(events)

    snapshot = RunReadService().build_run_snapshot(payload.run_id)
    if snapshot is None:
        raise RuntimeError(f"Run snapshot {payload.run_id} not found after workflow start")

    await get_dashboard_event_publisher().publish(
        DashboardWorkflowStartedEvent(
            run_id=payload.run_id,
            definition_id=payload.definition_id,
            workflow_name=initialized.benchmark_type,
            snapshot=snapshot,
            started_at=snapshot.started_at or utcnow(),
            total_tasks=snapshot.total_tasks,
            total_leaf_tasks=snapshot.total_leaf_tasks,
        )
    )

    result = WorkflowStartResult(
        run_id=payload.run_id,
        initial_ready_tasks=len(initialized.initial_ready_tasks),
        total_tasks=initialized.total_tasks,
    )

    get_trace_sink().emit_span(
        CompletedSpan(
            name="workflow.start",
            context=workflow_start_context(payload.run_id),
            start_time=span_start,
            end_time=datetime.now(UTC),
            attributes={
                "run_id": str(payload.run_id),
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
