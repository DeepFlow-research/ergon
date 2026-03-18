"""Workflow start Inngest function.

Initializes DAG execution when a workflow starts.
"""

from functools import partial
from uuid import UUID

import inngest

from h_arcane.core._internal.db.models import RunStatus
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.task.events import TaskReadyEvent, WorkflowStartedEvent
from h_arcane.core._internal.task.propagation import (
    get_initial_ready_tasks,
    mark_task_ready,
)
from h_arcane.core._internal.task.results import (
    DagInitResult,
    ReadyTaskIdsResult,
    WorkflowStartResult,
)
from h_arcane.core._internal.task.schema import TaskTreeNode, parse_task_tree
from h_arcane.core._internal.utils import require_not_none, utcnow
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
    run_id = UUID(payload.run_id)
    experiment_id = UUID(payload.experiment_id)

    # Inline: Load experiment (pure read, safe to re-run)
    experiment = require_not_none(
        queries.experiments.get(experiment_id),
        f"Experiment {experiment_id} not found",
    )
    tree = parse_task_tree(experiment.task_tree)
    if tree is None:
        raise ValueError(f"Experiment {experiment_id} has no task_tree")

    # Initialize task states and evaluators
    init_result = await ctx.step.run(
        "initialize-dag",
        partial(_initialize_dag, run_id, tree),
        output_type=DagInitResult,
    )
    init_result = require_not_none(init_result, "initialize-dag returned None")

    # Mark run as EXECUTING
    await ctx.step.run("mark-executing", partial(_mark_run_executing, run_id))

    # Emit dashboard workflow started event
    await ctx.step.run(
        "emit-dashboard-workflow-started",
        partial(_emit_dashboard_workflow_started, run_id, experiment_id, tree),
    )

    # Find and mark initial ready tasks
    ready_result = await ctx.step.run(
        "get-initial-ready-tasks",
        partial(_get_and_mark_initial_tasks, run_id, tree),
        output_type=ReadyTaskIdsResult,
    )
    ready_result = require_not_none(ready_result, "get-initial-ready-tasks returned None")
    ready_task_ids = ready_result.ready_task_ids

    # Emit task/ready events for each initial task (in parallel)
    # Keep as closure - dynamic parallel step needs closure capture for dynamic IDs
    if ready_task_ids:

        def make_emit_step(tid: UUID):
            async def emit_task_ready() -> None:
                event = TaskReadyEvent(
                    run_id=str(run_id),
                    experiment_id=str(experiment_id),
                    task_id=str(tid),
                )
                await inngest_client.send(
                    inngest.Event(name=TaskReadyEvent.name, data=event.model_dump())
                )

            return partial(ctx.step.run, f"emit-task-ready-{tid}", emit_task_ready)

        await ctx.group.parallel(tuple(make_emit_step(tid) for tid in ready_task_ids))

    return WorkflowStartResult(
        run_id=run_id,
        dependencies_created=init_result.dependency_count,
        evaluators_created=init_result.evaluator_count,
        initial_ready_tasks=len(ready_task_ids),
    )


async def _initialize_dag(run_id: UUID, tree: TaskTreeNode) -> DagInitResult:
    """Record initial PENDING state for all tasks and create TaskEvaluator records.

    Also emits dashboard task_status_changed for each task -> PENDING.
    """
    evaluator_count = 0

    # Record initial PENDING state for all tasks (event sourcing)
    # This ensures the event log is complete from workflow start
    for task_node in tree.walk():
        queries.task_state_events.record_state_change(
            run_id=run_id,
            task_id=UUID(task_node.id),
            new_status="pending",
            old_status=None,
            triggered_by=TaskTrigger.WORKFLOW_STARTED.value,
        )
        # Emit dashboard event for initial pending state
        await dashboard_emitter.task_status_changed(
            run_id=run_id,
            task_id=UUID(task_node.id),
            task_name=task_node.name,
            old_status=None,
            new_status=TaskStatus.PENDING,
            parent_task_id=task_node.parent_id,
            triggered_by=TaskTrigger.WORKFLOW_STARTED,
        )

    # Count dependencies from task_tree (for logging/metrics only)
    dependency_count = len(tree.extract_dependencies())

    # Create TaskEvaluator records
    for task_id_str, eval_ref in tree.extract_evaluators():
        evaluator_data = eval_ref.model_dump()
        evaluator_config = dict(evaluator_data)
        evaluator_type = evaluator_config.pop("type", "unknown")
        queries.task_evaluators.create_evaluator(
            run_id=run_id,
            task_id=UUID(task_id_str),
            evaluator_type=evaluator_type,
            evaluator_config=evaluator_config,
        )
        evaluator_count += 1

    return DagInitResult(
        dependency_count=dependency_count,
        evaluator_count=evaluator_count,
    )


async def _mark_run_executing(run_id: UUID) -> None:
    """Mark run status as EXECUTING with timestamp."""
    run = queries.runs.get(run_id)
    if run:
        run.status = RunStatus.EXECUTING
        run.started_at = utcnow()
        queries.runs.update(run)


async def _emit_dashboard_workflow_started(
    run_id: UUID, experiment_id: UUID, tree: TaskTreeNode
) -> None:
    """Emit dashboard workflow started event with task tree."""
    await dashboard_emitter.workflow_started(
        run_id=run_id,
        experiment_id=experiment_id,
        workflow_name=tree.name,
        task_tree=tree,
        total_tasks=len(list(tree.walk())),
        total_leaf_tasks=len(tree.get_leaf_ids()),
    )


async def _get_and_mark_initial_tasks(run_id: UUID, tree: TaskTreeNode) -> ReadyTaskIdsResult:
    """Find initial ready tasks, mark them, emit dashboard READY events."""
    ready_task_ids = get_initial_ready_tasks(run_id)
    for tid in ready_task_ids:
        mark_task_ready(run_id, tid, triggered_by=TaskTrigger.WORKFLOW_STARTED)
        # Emit dashboard event for ready state
        task_name = f"Task {tid}"
        task_node = tree.find_by_id(str(tid))
        if task_node:
            task_name = task_node.name

        await dashboard_emitter.task_status_changed(
            run_id=run_id,
            task_id=tid,
            task_name=task_name,
            old_status=TaskStatus.PENDING,
            new_status=TaskStatus.READY,
            triggered_by=TaskTrigger.WORKFLOW_STARTED,
        )
    return ReadyTaskIdsResult(ready_task_ids=ready_task_ids)
