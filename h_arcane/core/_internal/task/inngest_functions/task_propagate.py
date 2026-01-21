"""Task propagation Inngest function.

Handles task completion and propagates through DAG.
"""

from datetime import datetime, timezone
from functools import partial
from uuid import UUID

import inngest

from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.task.events import (
    TaskCompletedEvent,
    TaskReadyEvent,
    WorkflowCompletedEvent,
    WorkflowFailedEvent,
)
from h_arcane.core._internal.task.propagation import (
    is_workflow_complete,
    is_workflow_failed,
    on_task_completed,
)
from h_arcane.core._internal.task.results import ReadyTaskIdsResult, TaskPropagateResult
from h_arcane.core._internal.task.schema import parse_task_tree
from h_arcane.core._internal.utils import require_not_none
from h_arcane.core.status import TaskStatus, TaskTrigger
from h_arcane.dashboard import dashboard_emitter


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
    run_id = UUID(payload.run_id)
    experiment_id = UUID(payload.experiment_id)
    task_id = UUID(payload.task_id)
    execution_id = UUID(payload.execution_id)

    # Load task tree for task names
    run = queries.runs.get(run_id)
    experiment = queries.experiments.get(experiment_id) if run else None
    tree = parse_task_tree(experiment.task_tree) if experiment else None

    def get_task_name(tid: UUID) -> str:
        """Get task name from tree or return default."""
        if tree:
            task_node = tree.find_by_id(str(tid))
            if task_node:
                return task_node.name
        return f"Task {tid}"

    def get_parent_id(tid: UUID) -> str | None:
        """Get parent task ID from tree."""
        if tree:
            task_node = tree.find_by_id(str(tid))
            if task_node:
                return task_node.parent_id
        return None

    # Call propagation logic (DB writes, must be in step)
    async def propagate() -> ReadyTaskIdsResult:
        ready_tasks = on_task_completed(run_id, task_id, execution_id)
        return ReadyTaskIdsResult(ready_task_ids=ready_tasks)

    prop_result = await ctx.step.run("propagate", propagate, output_type=ReadyTaskIdsResult)
    prop_result = require_not_none(prop_result, "propagate returned None")
    ready_task_ids = prop_result.ready_task_ids

    # Emit task/ready for each newly ready task (in parallel)
    if ready_task_ids:

        def make_emit_step(tid: UUID):
            async def emit_ready() -> None:
                event = TaskReadyEvent(
                    run_id=str(run_id),
                    experiment_id=str(experiment_id),
                    task_id=str(tid),
                )
                await inngest_client.send(
                    inngest.Event(name=TaskReadyEvent.name, data=event.model_dump())
                )
                # Emit dashboard task ready event
                await dashboard_emitter.task_status_changed(
                    run_id=run_id,
                    task_id=tid,
                    task_name=get_task_name(tid),
                    old_status=TaskStatus.PENDING,
                    new_status=TaskStatus.READY,
                    parent_task_id=get_parent_id(tid),
                    triggered_by=TaskTrigger.DEPENDENCY_SATISFIED,
                )

            return partial(ctx.step.run, f"emit-ready-{tid}", emit_ready)

        await ctx.group.parallel(tuple(make_emit_step(tid) for tid in ready_task_ids))

    # Check workflow status (inlined - pure reads, safe to re-run on retry)
    workflow_complete = is_workflow_complete(run_id)
    workflow_failed = is_workflow_failed(run_id)

    # Emit workflow event if terminal state
    if workflow_complete:

        async def emit_workflow_completed() -> None:
            event = WorkflowCompletedEvent(
                run_id=str(run_id),
                experiment_id=str(experiment_id),
            )
            await inngest_client.send(
                inngest.Event(name=WorkflowCompletedEvent.name, data=event.model_dump())
            )

        await ctx.step.run("emit-workflow-completed", emit_workflow_completed)
    elif workflow_failed:

        async def emit_workflow_failed() -> None:
            event = WorkflowFailedEvent(
                run_id=str(run_id),
                experiment_id=str(experiment_id),
                error="One or more tasks failed",
            )
            await inngest_client.send(
                inngest.Event(name=WorkflowFailedEvent.name, data=event.model_dump())
            )
            # Emit dashboard workflow failed event
            run = queries.runs.get(run_id)
            if run:
                started_at = run.started_at or run.created_at
                duration_seconds = (datetime.now(timezone.utc) - started_at).total_seconds()
                await dashboard_emitter.workflow_completed(
                    run_id=run_id,
                    status="failed",
                    duration_seconds=duration_seconds,
                    error="One or more tasks failed",
                )

        await ctx.step.run("emit-workflow-failed", emit_workflow_failed)

    return TaskPropagateResult(
        run_id=run_id,
        task_id=task_id,
        newly_ready_tasks=len(ready_task_ids),
        workflow_complete=workflow_complete,
        workflow_failed=workflow_failed,
    )
