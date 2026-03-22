"""Task propagation Inngest function.

Handles task completion and propagates through DAG.
"""

from functools import partial
from uuid import UUID

import inngest

from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.infrastructure.tracing import get_trace_sink, task_execute_context
from h_arcane.core._internal.task.events import (
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskReadyEvent,
    WorkflowCompletedEvent,
    WorkflowFailedEvent,
)
from h_arcane.core._internal.task.results import TaskPropagateResult
from h_arcane.core._internal.task.services import TaskPropagationService
from h_arcane.core._internal.task.services.dto import (
    PropagateTaskCompletionCommand,
    PropagationResult,
    TaskDescriptor,
    WorkflowTerminalState,
)
from h_arcane.core.status import TaskStatus, TaskTrigger
from h_arcane.core.dashboard import dashboard_emitter


@inngest_client.create_function(
    fn_id="task-propagate",
    trigger=inngest.TriggerEvent(event=TaskCompletedEvent.name),
    retries=1,
    output_type=TaskPropagateResult,
)
async def task_propagate(ctx: inngest.Context) -> TaskPropagateResult:
    """
    Handle task completion - propagate through DAG.

    This function:
    1. Calls on_task_completed() to update deps and find ready tasks
    2. Emits task/ready for each newly ready task
    3. Checks if workflow is complete/failed (inlined)
    4. If terminal state, emits workflow event
    """
    payload = TaskCompletedEvent.model_validate(ctx.event.data)
    run_id = payload.run_id
    experiment_id = payload.experiment_id
    task_id = payload.task_id
    execution_id = payload.execution_id

    prop_result: PropagationResult = await ctx.step.run(
        "propagate",
        partial(_propagate, run_id, experiment_id, task_id, execution_id),
        output_type=PropagationResult,
    )

    # Emit task/ready for each newly ready task (in parallel)
    if prop_result.ready_tasks:

        def make_emit_step(task: TaskDescriptor):
            return partial(
                ctx.step.run,
                f"emit-ready-{task.task_id}",
                lambda: _emit_ready_and_dashboard(run_id, experiment_id, task),
            )

        await ctx.group.parallel(tuple(make_emit_step(task) for task in prop_result.ready_tasks))

    # Emit workflow event if terminal state
    workflow_complete = prop_result.workflow_terminal_state == WorkflowTerminalState.COMPLETED
    workflow_failed = prop_result.workflow_terminal_state == WorkflowTerminalState.FAILED

    if workflow_complete:
        await ctx.step.run(
            "emit-workflow-completed",
            partial(_emit_workflow_completed, run_id, experiment_id),
        )
    elif workflow_failed:
        await ctx.step.run(
            "emit-workflow-failed",
            partial(_emit_workflow_failed, run_id, experiment_id),
        )

    return TaskPropagateResult(
        run_id=run_id,
        task_id=task_id,
        newly_ready_tasks=len(prop_result.ready_tasks),
        workflow_complete=workflow_complete,
        workflow_failed=workflow_failed,
    )


@inngest_client.create_function(
    fn_id="task-failure-propagate",
    trigger=inngest.TriggerEvent(event=TaskFailedEvent.name),
    retries=1,
    output_type=TaskPropagateResult,
)
async def task_failure_propagate(ctx: inngest.Context) -> TaskPropagateResult:
    """
    Handle task failure and emit workflow/failed when the run becomes terminal.

    Failed tasks never unlock downstream work, but they do need to push the run
    into a failed terminal state so cohort counts and run views converge.
    """
    payload = TaskFailedEvent.model_validate(ctx.event.data)
    run_id = payload.run_id
    experiment_id = payload.experiment_id
    task_id = payload.task_id
    execution_id = payload.execution_id

    prop_result: PropagationResult = await ctx.step.run(
        "propagate-failure",
        partial(_propagate_failure, run_id, experiment_id, task_id, execution_id),
        output_type=PropagationResult,
    )

    workflow_failed = prop_result.workflow_terminal_state == WorkflowTerminalState.FAILED

    if workflow_failed:
        await ctx.step.run(
            "emit-workflow-failed",
            partial(_emit_workflow_failed, run_id, experiment_id),
        )

    return TaskPropagateResult(
        run_id=run_id,
        task_id=task_id,
        newly_ready_tasks=0,
        workflow_complete=False,
        workflow_failed=workflow_failed,
    )


async def _emit_ready_and_dashboard(
    run_id: UUID,
    experiment_id: UUID,
    task: TaskDescriptor,
) -> None:
    """Emit task/ready event and dashboard READY state for one task."""
    event = TaskReadyEvent(
        run_id=run_id,
        experiment_id=experiment_id,
        task_id=task.task_id,
    )
    await inngest_client.send(
        inngest.Event(name=TaskReadyEvent.name, data=event.model_dump(mode="json"))
    )
    await dashboard_emitter.task_status_changed(
        run_id=run_id,
        task_id=task.task_id,
        task_name=task.task_name,
        old_status=TaskStatus.PENDING,
        new_status=TaskStatus.READY,
        parent_task_id=task.parent_task_id,
        triggered_by=TaskTrigger.DEPENDENCY_SATISFIED,
    )


async def _propagate(
    run_id: UUID,
    experiment_id: UUID,
    task_id: UUID,
    execution_id: UUID,
) -> PropagationResult:
    """Run propagation service for a completed task."""
    return TaskPropagationService(
        trace_sink=get_trace_sink(),
        trace_context=task_execute_context(
            run_id,
            task_id,
            execution_id=execution_id,
            attributes={"experiment_id": experiment_id},
        ),
    ).propagate(
        PropagateTaskCompletionCommand(
            run_id=run_id,
            experiment_id=experiment_id,
            task_id=task_id,
            execution_id=execution_id,
        )
    )


async def _propagate_failure(
    run_id: UUID,
    experiment_id: UUID,
    task_id: UUID,
    execution_id: UUID,
) -> PropagationResult:
    """Run propagation service for a failed task."""
    return TaskPropagationService(
        trace_sink=get_trace_sink(),
        trace_context=task_execute_context(
            run_id,
            task_id,
            execution_id=execution_id,
            attributes={"experiment_id": experiment_id},
        ),
    ).propagate_failure(
        PropagateTaskCompletionCommand(
            run_id=run_id,
            experiment_id=experiment_id,
            task_id=task_id,
            execution_id=execution_id,
        )
    )


async def _emit_workflow_completed(run_id: UUID, experiment_id: UUID) -> None:
    """Emit WorkflowCompletedEvent (Inngest only, dashboard emitted in workflow_complete)."""
    event = WorkflowCompletedEvent(
        run_id=run_id,
        experiment_id=experiment_id,
    )
    await inngest_client.send(
        inngest.Event(name=WorkflowCompletedEvent.name, data=event.model_dump(mode="json"))
    )


async def _emit_workflow_failed(run_id: UUID, experiment_id: UUID) -> None:
    """Emit WorkflowFailedEvent (dashboard emission happens in workflow_failed)."""
    event = WorkflowFailedEvent(
        run_id=run_id,
        experiment_id=experiment_id,
        error="One or more tasks failed",
    )
    await inngest_client.send(
        inngest.Event(name=WorkflowFailedEvent.name, data=event.model_dump(mode="json"))
    )
