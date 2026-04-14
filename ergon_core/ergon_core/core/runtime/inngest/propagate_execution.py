"""Inngest functions: task completion propagation and failure propagation.

Resolves DAG dependencies and detects workflow terminal states.
"""

import logging
from datetime import UTC, datetime

import inngest
from ergon_core.core.runtime.events.task_events import (
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskReadyEvent,
    WorkflowCompletedEvent,
    WorkflowFailedEvent,
)
from ergon_core.core.runtime.inngest_client import RUN_CANCEL, inngest_client
from ergon_core.core.runtime.services.inngest_function_results import TaskPropagateResult
from ergon_core.core.runtime.services.orchestration_dto import (
    PropagateTaskCompletionCommand,
    WorkflowTerminalState,
)
from ergon_core.core.runtime.services.task_propagation_service import (
    TaskPropagationService,
)
from ergon_core.core.runtime.tracing import (
    CompletedSpan,
    get_trace_sink,
    task_propagate_context,
)

logger = logging.getLogger(__name__)


@inngest_client.create_function(
    fn_id="task-propagate",
    trigger=inngest.TriggerEvent(event="task/completed"),
    cancel=RUN_CANCEL,
    retries=1,
    output_type=TaskPropagateResult,
)
async def propagate_task_fn(ctx: inngest.Context) -> TaskPropagateResult:
    payload = TaskCompletedEvent.model_validate(ctx.event.data)
    logger.info("task-propagate run_id=%s task_id=%s", payload.run_id, payload.task_id)
    span_start = datetime.now(UTC)

    svc = TaskPropagationService()
    propagation = svc.propagate(
        PropagateTaskCompletionCommand(
            run_id=payload.run_id,
            definition_id=payload.definition_id,
            task_id=payload.task_id,
            execution_id=payload.execution_id,
            node_id=payload.node_id,
        )
    )

    events: list[inngest.Event] = [
        inngest.Event(
            name=TaskReadyEvent.name,
            data=TaskReadyEvent(
                run_id=payload.run_id,
                definition_id=payload.definition_id,
                task_id=td.task_id,
                node_id=td.node_id,
            ).model_dump(mode="json"),
        )
        for td in propagation.ready_tasks
    ]

    if propagation.workflow_terminal_state == WorkflowTerminalState.COMPLETED:
        events.append(
            inngest.Event(
                name=WorkflowCompletedEvent.name,
                data=WorkflowCompletedEvent(
                    run_id=payload.run_id,
                    definition_id=payload.definition_id,
                ).model_dump(mode="json"),
            )
        )
    elif propagation.workflow_terminal_state == WorkflowTerminalState.FAILED:
        events.append(
            inngest.Event(
                name=WorkflowFailedEvent.name,
                data=WorkflowFailedEvent(
                    run_id=payload.run_id,
                    definition_id=payload.definition_id,
                    error="Workflow failed during task propagation",
                ).model_dump(mode="json"),
            )
        )

    if events:
        await inngest_client.send(events)

    result = TaskPropagateResult(
        run_id=payload.run_id,
        task_id=payload.task_id,
        newly_ready_tasks=len(propagation.ready_tasks),
        workflow_complete=(propagation.workflow_terminal_state == WorkflowTerminalState.COMPLETED),
        workflow_failed=(propagation.workflow_terminal_state == WorkflowTerminalState.FAILED),
    )

    get_trace_sink().emit_span(
        CompletedSpan(
            name="task.propagate",
            context=task_propagate_context(payload.run_id, payload.task_id),
            start_time=span_start,
            end_time=datetime.now(UTC),
            attributes={
                "run_id": str(payload.run_id),
                "task_id": str(payload.task_id),
                "newly_ready_tasks": len(propagation.ready_tasks),
                "workflow_terminal": str(propagation.workflow_terminal_state),
            },
        )
    )

    return result


@inngest_client.create_function(
    fn_id="task-failure-propagate",
    trigger=inngest.TriggerEvent(event="task/failed"),
    cancel=RUN_CANCEL,
    retries=1,
    output_type=TaskPropagateResult,
)
async def propagate_task_failure_fn(ctx: inngest.Context) -> TaskPropagateResult:
    payload = TaskFailedEvent.model_validate(ctx.event.data)
    logger.info(
        "task-failure-propagate run_id=%s task_id=%s error=%s",
        payload.run_id,
        payload.task_id,
        payload.error,
    )

    svc = TaskPropagationService()
    propagation = svc.propagate_failure(
        PropagateTaskCompletionCommand(
            run_id=payload.run_id,
            definition_id=payload.definition_id,
            task_id=payload.task_id,
            execution_id=payload.execution_id,
            node_id=payload.node_id,
        )
    )

    if propagation.workflow_terminal_state == WorkflowTerminalState.FAILED:
        await inngest_client.send(
            inngest.Event(
                name=WorkflowFailedEvent.name,
                data=WorkflowFailedEvent(
                    run_id=payload.run_id,
                    definition_id=payload.definition_id,
                    error=payload.error,
                ).model_dump(mode="json"),
            )
        )

    result = TaskPropagateResult(
        run_id=payload.run_id,
        task_id=payload.task_id,
        newly_ready_tasks=0,
        workflow_complete=False,
        workflow_failed=(propagation.workflow_terminal_state == WorkflowTerminalState.FAILED),
    )
    return result
