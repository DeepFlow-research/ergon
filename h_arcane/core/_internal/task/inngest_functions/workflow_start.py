"""Workflow start Inngest function.

Initializes DAG execution when a workflow starts.
"""

from functools import partial
from uuid import UUID

import inngest

from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.infrastructure.tracing import (
    CompletedSpan,
    get_trace_sink,
    workflow_start_context,
)
from h_arcane.core._internal.task.events import TaskReadyEvent, WorkflowStartedEvent
from h_arcane.core._internal.task.results import WorkflowStartResult
from h_arcane.core._internal.task.services import WorkflowInitializationService
from h_arcane.core._internal.task.services.dto import (
    InitializeWorkflowCommand,
    InitializedWorkflow,
    TaskDescriptor,
)
from h_arcane.core._internal.utils import utcnow
from h_arcane.core.status import TaskStatus, TaskTrigger
from h_arcane.core.dashboard import dashboard_emitter


@inngest_client.create_function(
    fn_id="workflow-start",
    trigger=inngest.TriggerEvent(event=WorkflowStartedEvent.name),
    retries=1,
    output_type=WorkflowStartResult,
)
async def workflow_start(ctx: inngest.Context) -> WorkflowStartResult:
    """
    Initialize DAG execution when a workflow starts.

    This function:
    1. Loads experiment and parses task_tree (inlined)
    2. Records initial PENDING state and creates TaskEvaluator records
    3. Marks run as EXECUTING
    4. Finds initial ready tasks
    5. Emits task/ready events

    Note: Dependencies are stored in task_tree JSON (depends_on field) and
    checked at runtime via TaskStateEvent.
    """
    payload = WorkflowStartedEvent.model_validate(ctx.event.data)
    run_id = payload.run_id
    experiment_id = payload.experiment_id
    trace_sink = get_trace_sink()
    trace_context = workflow_start_context(
        run_id,
        attributes={"experiment_id": experiment_id},
    )
    started_at = utcnow()

    initialized = await ctx.step.run(
        "initialize-workflow",
        lambda: WorkflowInitializationService(
            trace_sink=trace_sink,
            trace_context=trace_context,
        ).initialize(
            InitializeWorkflowCommand(run_id=run_id, experiment_id=experiment_id)
        ),
        output_type=InitializedWorkflow,
    )

    # Emit dashboard workflow started event
    await ctx.step.run(
        "emit-dashboard-workflow-started",
        partial(_emit_dashboard_workflow_started, initialized),
    )

    if initialized.pending_tasks:
        def make_pending_step(task: TaskDescriptor):
            return partial(ctx.step.run, f"emit-task-pending-{task.task_id}", lambda: _emit_task_pending(run_id, task))

        await ctx.group.parallel(tuple(make_pending_step(task) for task in initialized.pending_tasks))

    if initialized.initial_ready_tasks:
        def make_ready_dashboard_step(task: TaskDescriptor):
            return partial(ctx.step.run, f"emit-task-ready-dashboard-{task.task_id}", lambda: _emit_task_ready_dashboard(run_id, task))

        await ctx.group.parallel(
            tuple(make_ready_dashboard_step(task) for task in initialized.initial_ready_tasks)
        )

    # Emit task/ready events for each initial task (in parallel)
    # Keep as closure - dynamic parallel step needs closure capture for dynamic IDs
    if initialized.initial_ready_tasks:

        def make_emit_step(task: TaskDescriptor):
            return partial(
                ctx.step.run,
                f"emit-task-ready-{task.task_id}",
                lambda: _emit_task_ready_event(run_id, experiment_id, task.task_id),
            )

        await ctx.group.parallel(tuple(make_emit_step(task) for task in initialized.initial_ready_tasks))

    trace_sink.emit_span(
        CompletedSpan(
            name="workflow.start",
            context=trace_context,
            start_time=started_at,
            end_time=utcnow(),
            attributes={
                "workflow_name": initialized.workflow_name,
                "total_tasks": initialized.total_tasks,
                "total_leaf_tasks": initialized.total_leaf_tasks,
                "dependency_count": initialized.dependency_count,
                "evaluator_count": initialized.evaluator_count,
                "initial_ready_count": len(initialized.initial_ready_tasks),
            },
        )
    )

    return WorkflowStartResult(
        run_id=run_id,
        dependencies_created=initialized.dependency_count,
        evaluators_created=initialized.evaluator_count,
        initial_ready_tasks=len(initialized.initial_ready_tasks),
    )


async def _emit_dashboard_workflow_started(initialized: InitializedWorkflow) -> None:
    """Emit dashboard workflow started event with task tree."""
    await dashboard_emitter.workflow_started(
        run_id=initialized.run_id,
        experiment_id=initialized.experiment_id,
        workflow_name=initialized.workflow_name,
        task_tree=initialized.task_tree,
        total_tasks=initialized.total_tasks,
        total_leaf_tasks=initialized.total_leaf_tasks,
    )


async def _emit_task_pending(run_id: UUID, task: TaskDescriptor) -> None:
    """Emit dashboard pending state for one task."""
    await dashboard_emitter.task_status_changed(
        run_id=run_id,
        task_id=task.task_id,
        task_name=task.task_name,
        old_status=None,
        new_status=TaskStatus.PENDING,
        parent_task_id=task.parent_task_id,
        triggered_by=TaskTrigger.WORKFLOW_STARTED,
    )


async def _emit_task_ready_dashboard(run_id: UUID, task: TaskDescriptor) -> None:
    """Emit dashboard ready state for one task."""
    await dashboard_emitter.task_status_changed(
        run_id=run_id,
        task_id=task.task_id,
        task_name=task.task_name,
        old_status=TaskStatus.PENDING,
        new_status=TaskStatus.READY,
        parent_task_id=task.parent_task_id,
        triggered_by=TaskTrigger.WORKFLOW_STARTED,
    )


async def _emit_task_ready_event(run_id: UUID, experiment_id: UUID, task_id: UUID) -> None:
    """Emit task/ready event for one initial task."""
    event = TaskReadyEvent(
        run_id=run_id,
        experiment_id=experiment_id,
        task_id=task_id,
    )
    await inngest_client.send(inngest.Event(name=TaskReadyEvent.name, data=event.model_dump()))
