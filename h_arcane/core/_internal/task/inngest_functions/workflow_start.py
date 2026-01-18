"""Workflow start Inngest function.

Initializes DAG execution when a workflow starts.
"""

from functools import partial
from datetime import datetime, timezone
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
from h_arcane.core._internal.task.schema import parse_task_tree
from h_arcane.core._internal.utils import require_not_none


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
    2. Creates TaskDependency and TaskEvaluator records (combined)
    3. Marks run as EXECUTING
    4. Finds initial ready tasks
    5. Emits task/ready events
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

    # Combined: Create dependencies + evaluators
    async def initialize_dag() -> DagInitResult:
        dependency_count = 0
        evaluator_count = 0

        if tree is None:
            return DagInitResult(dependency_count=0, evaluator_count=0)

        # Create TaskDependency records
        str_deps = tree.extract_dependencies()
        dependencies = [(UUID(dep), UUID(target)) for dep, target in str_deps]
        if dependencies:
            queries.task_dependencies.create_for_run(run_id, dependencies)
        dependency_count = len(dependencies)

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

    init_result = await ctx.step.run("initialize-dag", initialize_dag, output_type=DagInitResult)
    init_result = require_not_none(init_result, "initialize-dag returned None")

    # Mark run as EXECUTING
    async def mark_run_executing() -> None:
        run = queries.runs.get(run_id)
        if run:
            run.status = RunStatus.EXECUTING
            run.started_at = datetime.now(timezone.utc)
            queries.runs.update(run)

    await ctx.step.run("mark-executing", mark_run_executing)

    # Find and mark initial ready tasks
    async def get_and_mark_initial_tasks() -> ReadyTaskIdsResult:
        ready_task_ids = get_initial_ready_tasks(run_id)
        for tid in ready_task_ids:
            mark_task_ready(run_id, tid, triggered_by="workflow_started")
        return ReadyTaskIdsResult(ready_task_ids=ready_task_ids)

    ready_result = await ctx.step.run(
        "get-initial-ready-tasks", get_and_mark_initial_tasks, output_type=ReadyTaskIdsResult
    )
    ready_result = require_not_none(ready_result, "get-initial-ready-tasks returned None")
    ready_task_ids = ready_result.ready_task_ids

    # Emit task/ready events for each initial task (in parallel)
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
