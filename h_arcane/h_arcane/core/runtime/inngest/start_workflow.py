"""Inngest function: workflow initialization and first-task dispatch."""

import logging
from datetime import UTC, datetime

import inngest
from h_arcane.core.runtime.events.task_events import (
    TaskReadyEvent,
    WorkflowStartedEvent,
)
from h_arcane.core.runtime.inngest_client import RUN_CANCEL, inngest_client
from h_arcane.core.runtime.services.inngest_function_results import WorkflowStartResult
from h_arcane.core.runtime.services.orchestration_dto import InitializeWorkflowCommand
from h_arcane.core.runtime.services.workflow_initialization_service import (
    WorkflowInitializationService,
)
from h_arcane.core.runtime.tracing import (
    CompletedSpan,
    get_trace_sink,
    workflow_start_context,
)

logger = logging.getLogger(__name__)


@inngest_client.create_function(
    fn_id="workflow-start",
    trigger=inngest.TriggerEvent(event="workflow/started"),
    cancel=RUN_CANCEL,
    retries=1,
    output_type=WorkflowStartResult,
)
async def start_workflow_fn(ctx: inngest.Context) -> WorkflowStartResult:
    payload = WorkflowStartedEvent(**ctx.event.data)
    logger.info("workflow-start run_id=%s definition_id=%s", payload.run_id, payload.definition_id)
    span_start = datetime.now(UTC)

    svc = WorkflowInitializationService()
    initialized = svc.initialize(
        InitializeWorkflowCommand(
            run_id=payload.run_id,
            definition_id=payload.definition_id,
        )
    )

    events = [
        inngest.Event(
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

    result = WorkflowStartResult(
        run_id=payload.run_id,
        initial_ready_tasks=len(initialized.initial_ready_tasks),
        total_tasks=initialized.total_tasks,
    )

    get_trace_sink().emit_span(CompletedSpan(
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
    ))

    logger.info(
        "workflow-start completed: %d initial tasks of %d total",
        result.initial_ready_tasks,
        result.total_tasks,
    )
    return result
