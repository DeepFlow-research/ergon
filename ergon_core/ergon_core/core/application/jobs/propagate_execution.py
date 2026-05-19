"""Inngest functions: task completion propagation and failure propagation.

Resolves DAG dependencies and detects workflow terminal states.
"""

import logging
from datetime import UTC, datetime

from ergon_core.core.application.jobs.models import TaskPropagateResult
from ergon_core.core.application.workflows.orchestration import (
    PropagateTaskCompletionCommand,
    WorkflowTerminalState,
)
from ergon_core.core.application.workflows.service import WorkflowService
from ergon_core.core.infrastructure.inngest.client import InngestEvent, inngest_client
from ergon_core.core.application.events.task_events import (
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskReadyEvent,
    WorkflowCompletedEvent,
    WorkflowFailedEvent,
)
from ergon_core.core.infrastructure.tracing import (
    CompletedSpan,
    get_trace_sink,
    task_propagate_context,
)

logger = logging.getLogger(__name__)


async def run_propagate_task_job(payload: TaskCompletedEvent) -> TaskPropagateResult:
    logger.info("task-propagate run_id=%s task_id=%s", payload.run_id, payload.task_id)
    span_start = datetime.now(UTC)

    svc = WorkflowService()
    propagation = await svc.propagate(
        PropagateTaskCompletionCommand(
            run_id=payload.run_id,
            definition_id=payload.definition_id,
            task_id=payload.task_id,
            execution_id=payload.execution_id,
        )
    )

    events: list[InngestEvent] = [
        InngestEvent(
            name=TaskReadyEvent.name,
            data=TaskReadyEvent(
                run_id=payload.run_id,
                definition_id=payload.definition_id,
                task_id=td.task_id,
            ).model_dump(mode="json"),
        )
        for td in propagation.ready_tasks
    ]

    if propagation.workflow_terminal_state == WorkflowTerminalState.COMPLETED:
        events.append(
            InngestEvent(
                name=WorkflowCompletedEvent.name,
                data=WorkflowCompletedEvent(
                    run_id=payload.run_id,
                    definition_id=payload.definition_id,
                ).model_dump(mode="json"),
            )
        )
    elif propagation.workflow_terminal_state == WorkflowTerminalState.FAILED:
        events.append(
            InngestEvent(
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


async def run_propagate_task_failure_job(payload: TaskFailedEvent) -> TaskPropagateResult:
    logger.info(
        "task-failure-propagate run_id=%s task_id=%s error=%s",
        payload.run_id,
        payload.task_id,
        payload.error,
    )

    svc = WorkflowService()
    propagation = await svc.propagate_failure(
        PropagateTaskCompletionCommand(
            run_id=payload.run_id,
            definition_id=payload.definition_id,
            task_id=payload.task_id,
            execution_id=payload.execution_id,
        )
    )

    # BLOCKED successors are a DB write only — no task/cancelled events.
    failure_events: list[InngestEvent] = []

    if propagation.workflow_terminal_state == WorkflowTerminalState.FAILED:
        failure_events.append(
            InngestEvent(
                name=WorkflowFailedEvent.name,
                data=WorkflowFailedEvent(
                    run_id=payload.run_id,
                    definition_id=payload.definition_id,
                    error=payload.error,
                ).model_dump(mode="json"),
            )
        )

    if failure_events:
        await inngest_client.send(failure_events)

    result = TaskPropagateResult(
        run_id=payload.run_id,
        task_id=payload.task_id,
        newly_ready_tasks=0,
        workflow_complete=False,
        workflow_failed=(propagation.workflow_terminal_state == WorkflowTerminalState.FAILED),
    )
    return result
