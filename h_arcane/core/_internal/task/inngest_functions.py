"""
Inngest functions for DAG-based workflow orchestration.

These functions handle the lifecycle of workflow execution:
- workflow_start: Initialize DAG, create dependencies, start initial tasks
- task_execute: Execute a single task with its assigned worker
- task_propagate: Handle completion, check dependencies, emit ready events
- workflow_complete: Finalize run, aggregate results, cleanup

Event flow:
    execute_task() -> workflow/started
                      -> workflow_start -> task/ready (for initial tasks)
                                           -> task_execute -> task/completed
                                                              -> task_propagate -> task/ready (next tasks)
                                                                                   ... repeat ...
                                                                                -> workflow/completed
                                                                                   -> workflow_complete
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, TypeVar
from uuid import UUID

import inngest

from h_arcane.core._internal.db.models import Experiment, RunStatus, TaskExecution
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.task.events import (
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskReadyEvent,
    WorkflowCompletedEvent,
    WorkflowFailedEvent,
    WorkflowStartedEvent,
)
from h_arcane.core._internal.task.propagation import (
    extract_dependencies_from_tree,
    get_initial_ready_tasks,
    get_leaf_descendants,
    is_workflow_complete,
    is_workflow_failed,
    mark_task_failed,
    mark_task_ready,
    mark_task_running,
    on_task_completed,
)
from h_arcane.core._internal.task.step_outputs import (
    DependencyCreationResult,
    EvaluatorCreationResult,
    LoadContextResult,
    PersistResult,
    PrepareExecutionResult,
    ReadyTaskIdsResult,
    ScoreAggregationResult,
    WorkflowStatusResult,
)

if TYPE_CHECKING:
    from h_arcane.core.worker import BaseWorker, WorkerContext

T = TypeVar("T")


def _require_not_none(value: T | None, error_msg: str) -> T:
    """Helper to raise error if value is None."""
    if value is None:
        raise ValueError(error_msg)
    return value


# =============================================================================
# workflow_start: Initialize DAG Execution
# =============================================================================


@inngest_client.create_function(
    fn_id="workflow-start",
    trigger=inngest.TriggerEvent(event=WorkflowStartedEvent.name),
    retries=1,
)
async def workflow_start(ctx: inngest.Context) -> dict:
    """
    Initialize DAG execution when a workflow starts.

    This function:
    1. Loads the task_tree from experiment
    2. Creates TaskDependency records
    3. Creates TaskEvaluator records for tasks with evaluators
    4. Marks run as EXECUTING
    5. Finds initial ready tasks (no dependencies)
    6. Emits task/ready events for each
    """
    payload = WorkflowStartedEvent.model_validate(ctx.event.data)
    run_id = UUID(payload.run_id)
    experiment_id = UUID(payload.experiment_id)

    # Load experiment to get task_tree
    async def load_experiment() -> Experiment:
        return _require_not_none(
            queries.experiments.get(experiment_id),
            f"Experiment {experiment_id} not found",
        )

    experiment = await ctx.step.run("load-experiment", load_experiment, output_type=Experiment)
    experiment = _require_not_none(experiment, "load-experiment returned None")
    task_tree = experiment.task_tree or {}

    # Create TaskDependency records
    async def create_dependencies() -> DependencyCreationResult:
        dependencies = extract_dependencies_from_tree(task_tree)
        if dependencies:
            queries.task_dependencies.create_for_run(run_id, dependencies)
        return DependencyCreationResult(dependency_count=len(dependencies))

    dep_result = await ctx.step.run(
        "create-dependencies", create_dependencies, output_type=DependencyCreationResult
    )
    dep_result = _require_not_none(dep_result, "create-dependencies returned None")

    # Create TaskEvaluator records for tasks with evaluators
    async def create_evaluators() -> EvaluatorCreationResult:
        created_count = 0
        # Walk the tree and find tasks with evaluators
        evaluators = _extract_evaluators_from_tree(task_tree)
        for task_id_str, evaluator_data in evaluators:
            queries.task_evaluators.create_evaluator(
                run_id=run_id,
                task_id=UUID(task_id_str),
                evaluator_type=evaluator_data.get("type", "unknown"),
                evaluator_config=evaluator_data,
            )
            created_count += 1
        return EvaluatorCreationResult(evaluator_count=created_count)

    eval_result = await ctx.step.run(
        "create-evaluators", create_evaluators, output_type=EvaluatorCreationResult
    )
    eval_result = _require_not_none(eval_result, "create-evaluators returned None")

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
    ready_result = _require_not_none(ready_result, "get-initial-ready-tasks returned None")
    ready_task_ids = ready_result.ready_task_ids

    # Emit task/ready events for each initial task
    for task_id in ready_task_ids:
        async def emit_task_ready(tid: UUID = task_id) -> None:
            event = TaskReadyEvent(
                run_id=str(run_id),
                experiment_id=str(experiment_id),
                task_id=str(tid),
            )
            await inngest_client.send(
                inngest.Event(name=TaskReadyEvent.name, data=event.model_dump())
            )

        await ctx.step.run(f"emit-task-ready-{task_id}", emit_task_ready)

    return {
        "run_id": str(run_id),
        "dependencies_created": dep_result.dependency_count,
        "evaluators_created": eval_result.evaluator_count,
        "initial_ready_tasks": len(ready_task_ids),
    }


def _extract_evaluators_from_tree(task_tree: dict) -> list[tuple[str, dict]]:
    """Extract (task_id, evaluator_config) pairs from task_tree."""
    evaluators: list[tuple[str, dict]] = []
    _walk_tree_for_evaluators(task_tree, evaluators)
    return evaluators


def _walk_tree_for_evaluators(task_data: dict, evaluators: list[tuple[str, dict]]) -> None:
    """Recursively walk tree and collect evaluator configs."""
    task_id = task_data.get("id")
    evaluator = task_data.get("evaluator")
    if task_id and evaluator:
        evaluators.append((str(task_id), evaluator))
    for child in task_data.get("children", []):
        _walk_tree_for_evaluators(child, evaluators)


# =============================================================================
# task_execute: Execute a Single Task
# =============================================================================


@inngest_client.create_function(
    fn_id="task-execute",
    trigger=inngest.TriggerEvent(event=TaskReadyEvent.name),
    retries=0,  # Tasks should not auto-retry (user decides retry strategy)
    concurrency=[inngest.Concurrency(limit=15, scope="fn")],
)
async def task_execute(ctx: inngest.Context) -> dict:
    """
    Execute a single task with its assigned worker.

    This function:
    1. Creates TaskExecution record
    2. Marks task as RUNNING
    3. Loads worker from task_tree + AgentConfig
    4. Executes worker.execute()
    5. Persists results (actions, outputs)
    6. Marks complete/failed
    7. Emits task/completed or task/failed
    """
    from h_arcane.core._internal.db.models import Run
    from h_arcane.core._internal.task.persistence import (
        complete_task_execution,
        create_task_execution,
        persist_actions,
        persist_output_resources,
    )
    from h_arcane.core.worker import WorkerContext, WorkerResult
    from h_arcane.core.task import Resource

    payload = TaskReadyEvent.model_validate(ctx.event.data)
    run_id = UUID(payload.run_id)
    experiment_id = UUID(payload.experiment_id)
    task_id = UUID(payload.task_id)

    # Load run and experiment
    async def load_context() -> LoadContextResult:
        run = _require_not_none(
            queries.runs.get(run_id),
            f"Run {run_id} not found",
        )
        exp = _require_not_none(
            queries.experiments.get(experiment_id),
            f"Experiment {experiment_id} not found",
        )
        return LoadContextResult(run=run, experiment=exp)

    context_result = await ctx.step.run(
        "load-context", load_context, output_type=LoadContextResult
    )
    context_result = _require_not_none(context_result, "load-context returned None")
    task_tree = context_result.experiment.task_tree or {}

    # Find task data in tree
    task_data = _find_task_in_tree(task_tree, str(task_id))
    if not task_data:
        raise ValueError(f"Task {task_id} not found in task_tree")

    # Create TaskExecution record
    async def create_execution() -> TaskExecution:
        return create_task_execution(run_id, task_id)

    execution = await ctx.step.run(
        "create-execution", create_execution, output_type=TaskExecution
    )
    execution = _require_not_none(execution, "create-execution returned None")
    execution_id = execution.id

    # Mark task as RUNNING
    async def mark_running() -> None:
        mark_task_running(run_id, task_id, execution_id)

    await ctx.step.run("mark-running", mark_running)

    try:
        # Get worker config and load input resources
        async def prepare_execution() -> PrepareExecutionResult:
            # Load agent config for this task's worker
            agent_configs = queries.agent_configs.get_by_run(run_id)

            # Get assigned worker ID from task_data
            assigned_to = task_data.get("assigned_to", {})

            # Find matching agent config
            agent_config_id: UUID | None = None
            for config in agent_configs:
                # Match by name (workers are stored by name in AgentConfig)
                if assigned_to and config.name == assigned_to.get("name"):
                    agent_config_id = config.id
                    break

            # Load input resources for this task
            input_resources = queries.resources.get_inputs_for_task(
                experiment_id, task_id
            )

            return PrepareExecutionResult(
                agent_config_id=agent_config_id,
                worker_data=assigned_to,
                input_resources=input_resources,
            )

        prep_result = await ctx.step.run(
            "prepare-execution", prepare_execution, output_type=PrepareExecutionResult
        )
        prep_result = _require_not_none(prep_result, "prepare-execution returned None")

        # Convert DB resources to SDK resources for WorkerContext
        sdk_resources = [
            Resource(
                name=r.name,
                path=r.file_path,
            )
            for r in prep_result.input_resources
        ]

        # Create worker context
        worker_context = WorkerContext(
            run_id=run_id,
            task_id=task_id,
            sandbox=None,  # TODO: Setup sandbox if needed
            input_resources=sdk_resources,
            metadata={
                "task_name": task_data.get("name"),
                "task_description": task_data.get("description"),
            },
        )

        # Execute the worker
        # NOTE: In the full implementation, we would instantiate the worker
        # from the worker_data and call worker.execute(). For now, we create
        # a stub result since we don't have the actual worker instance.
        async def execute_worker() -> WorkerResult:
            # TODO: Full worker execution implementation
            # This is a placeholder - in production, we would:
            # 1. Load the worker class from registry or task_data
            # 2. Instantiate with the stored config
            # 3. Call worker.execute(task, context)

            # For now, return a successful stub result
            return WorkerResult(
                success=True,
                actions=[],
                outputs=[],
                output_text=f"Task {task_data.get('name')} executed successfully",
            )

        worker_result = await ctx.step.run(
            "execute-worker", execute_worker, output_type=WorkerResult
        )
        worker_result = _require_not_none(worker_result, "execute-worker returned None")

        # Persist actions and outputs
        async def persist_results() -> PersistResult:
            # Persist actions
            if worker_result.actions and prep_result.agent_config_id:
                persist_actions(run_id, prep_result.agent_config_id, worker_result.actions)

            # Persist output resources
            output_resource_ids: list[UUID] = []
            if worker_result.outputs:
                output_resource_ids = persist_output_resources(
                    run_id, task_id, execution_id, worker_result.outputs
                )

            # Complete the task execution
            complete_task_execution(
                execution_id=execution_id,
                success=worker_result.success,
                output_text=worker_result.output_text,
                output_resource_ids=output_resource_ids,
            )

            return PersistResult(
                actions_count=len(worker_result.actions),
                outputs_count=len(output_resource_ids),
            )

        persist_result = await ctx.step.run(
            "persist-results", persist_results, output_type=PersistResult
        )
        persist_result = _require_not_none(persist_result, "persist-results returned None")

        # Emit task/completed event
        async def emit_completed() -> None:
            event = TaskCompletedEvent(
                run_id=str(run_id),
                experiment_id=str(experiment_id),
                task_id=str(task_id),
                execution_id=str(execution_id),
            )
            await inngest_client.send(
                inngest.Event(name=TaskCompletedEvent.name, data=event.model_dump())
            )

        await ctx.step.run("emit-completed", emit_completed)

        return {
            "run_id": str(run_id),
            "task_id": str(task_id),
            "execution_id": str(execution_id),
            "success": True,
            "actions_count": persist_result.actions_count,
            "outputs_count": persist_result.outputs_count,
        }

    except Exception as exc:
        error_msg = str(exc)

        # Mark task as failed
        async def mark_failed_task() -> None:
            mark_task_failed(run_id, task_id, error=error_msg, execution_id=execution_id)
            complete_task_execution(
                execution_id=execution_id,
                success=False,
                error_message=error_msg,
            )

        await ctx.step.run("mark-failed", mark_failed_task)

        # Emit task/failed event
        async def emit_failed() -> None:
            event = TaskFailedEvent(
                run_id=str(run_id),
                experiment_id=str(experiment_id),
                task_id=str(task_id),
                execution_id=str(execution_id),
                error=error_msg,
            )
            await inngest_client.send(
                inngest.Event(name=TaskFailedEvent.name, data=event.model_dump())
            )

        await ctx.step.run("emit-failed", emit_failed)

        raise inngest.NonRetriableError(f"Task execution failed: {error_msg}")


def _find_task_in_tree(task_tree: dict, task_id: str) -> dict | None:
    """Find a task by ID in the task_tree."""
    if str(task_tree.get("id")) == task_id:
        return task_tree
    for child in task_tree.get("children", []):
        found = _find_task_in_tree(child, task_id)
        if found:
            return found
    return None


# =============================================================================
# task_propagate: Handle Completion and Emit Ready Events
# =============================================================================


@inngest_client.create_function(
    fn_id="task-propagate",
    trigger=inngest.TriggerEvent(event=TaskCompletedEvent.name),
    retries=1,
)
async def task_propagate(ctx: inngest.Context) -> dict:
    """
    Handle task completion - propagate through DAG.

    This function:
    1. Calls on_task_completed() to update deps and find ready tasks
    2. Emits task/ready for each newly ready task
    3. Checks if workflow is complete
    4. If complete, emits workflow/completed
    """
    payload = TaskCompletedEvent.model_validate(ctx.event.data)
    run_id = UUID(payload.run_id)
    experiment_id = UUID(payload.experiment_id)
    task_id = UUID(payload.task_id)
    execution_id = UUID(payload.execution_id)

    # Call propagation logic
    async def propagate() -> ReadyTaskIdsResult:
        ready_tasks = on_task_completed(run_id, task_id, execution_id)
        return ReadyTaskIdsResult(ready_task_ids=ready_tasks)

    prop_result = await ctx.step.run(
        "propagate", propagate, output_type=ReadyTaskIdsResult
    )
    prop_result = _require_not_none(prop_result, "propagate returned None")
    ready_task_ids = prop_result.ready_task_ids

    # Emit task/ready for each newly ready task
    for ready_task_id in ready_task_ids:
        async def emit_ready(tid: UUID = ready_task_id) -> None:
            event = TaskReadyEvent(
                run_id=str(run_id),
                experiment_id=str(experiment_id),
                task_id=str(tid),
            )
            await inngest_client.send(
                inngest.Event(name=TaskReadyEvent.name, data=event.model_dump())
            )

        await ctx.step.run(f"emit-ready-{ready_task_id}", emit_ready)

    # Check if workflow is complete
    async def check_workflow_status() -> WorkflowStatusResult:
        complete = is_workflow_complete(run_id)
        failed = is_workflow_failed(run_id)
        return WorkflowStatusResult(complete=complete, failed=failed)

    status_result = await ctx.step.run(
        "check-workflow-status", check_workflow_status, output_type=WorkflowStatusResult
    )
    status_result = _require_not_none(status_result, "check-workflow-status returned None")

    # Emit workflow event if terminal state
    if status_result.complete:
        async def emit_workflow_completed() -> None:
            event = WorkflowCompletedEvent(
                run_id=str(run_id),
                experiment_id=str(experiment_id),
            )
            await inngest_client.send(
                inngest.Event(name=WorkflowCompletedEvent.name, data=event.model_dump())
            )

        await ctx.step.run("emit-workflow-completed", emit_workflow_completed)
    elif status_result.failed:
        async def emit_workflow_failed() -> None:
            event = WorkflowFailedEvent(
                run_id=str(run_id),
                experiment_id=str(experiment_id),
                error="One or more tasks failed",
            )
            await inngest_client.send(
                inngest.Event(name=WorkflowFailedEvent.name, data=event.model_dump())
            )

        await ctx.step.run("emit-workflow-failed", emit_workflow_failed)

    return {
        "run_id": str(run_id),
        "task_id": str(task_id),
        "newly_ready_tasks": len(ready_task_ids),
        "workflow_complete": status_result.complete,
        "workflow_failed": status_result.failed,
    }


# =============================================================================
# workflow_complete: Finalize Run
# =============================================================================


@inngest_client.create_function(
    fn_id="workflow-complete",
    trigger=inngest.TriggerEvent(event=WorkflowCompletedEvent.name),
    retries=1,
)
async def workflow_complete(ctx: inngest.Context) -> dict:
    """
    Finalize workflow when all tasks complete.

    This function:
    1. Marks Run as COMPLETED
    2. Aggregates scores from TaskEvaluators
    3. Updates Run with final results
    4. Triggers cleanup (sandbox termination)
    """
    from h_arcane.core._internal.infrastructure.events import RunCleanupEvent

    payload = WorkflowCompletedEvent.model_validate(ctx.event.data)
    run_id = UUID(payload.run_id)

    # Mark run as completed
    async def mark_completed() -> None:
        run = queries.runs.get(run_id)
        if run:
            run.status = RunStatus.COMPLETED
            run.completed_at = datetime.now(timezone.utc)
            queries.runs.update(run)

    await ctx.step.run("mark-completed", mark_completed)

    # Aggregate scores from task evaluators
    async def aggregate_scores() -> ScoreAggregationResult:
        evaluators = queries.task_evaluators.get_by_run(run_id)
        completed_evaluators = [e for e in evaluators if e.status == "completed"]

        if not completed_evaluators:
            return ScoreAggregationResult(final_score=None, normalized_score=None)

        total_score = sum(e.score or 0 for e in completed_evaluators)
        max_possible = len(completed_evaluators)  # Assuming max 1.0 per evaluator
        normalized_score = total_score / max_possible if max_possible > 0 else 0

        # Update run with scores
        run = queries.runs.get(run_id)
        if run:
            run.final_score = total_score
            run.normalized_score = normalized_score
            queries.runs.update(run)

        return ScoreAggregationResult(
            final_score=total_score,
            normalized_score=normalized_score,
            evaluators_count=len(completed_evaluators),
        )

    score_result = await ctx.step.run(
        "aggregate-scores", aggregate_scores, output_type=ScoreAggregationResult
    )
    score_result = _require_not_none(score_result, "aggregate-scores returned None")

    # Emit cleanup event
    async def emit_cleanup() -> None:
        event = RunCleanupEvent(
            run_id=str(run_id),
            status="completed",
        )
        await inngest_client.send(
            inngest.Event(name=RunCleanupEvent.name, data=event.model_dump())
        )

    await ctx.step.run("emit-cleanup", emit_cleanup)

    return {
        "run_id": str(run_id),
        "status": "completed",
        "final_score": score_result.final_score,
        "normalized_score": score_result.normalized_score,
    }


# =============================================================================
# workflow_failed: Handle Workflow Failure
# =============================================================================


@inngest_client.create_function(
    fn_id="workflow-failed",
    trigger=inngest.TriggerEvent(event=WorkflowFailedEvent.name),
    retries=0,
)
async def workflow_failed(ctx: inngest.Context) -> dict:
    """
    Handle workflow failure.

    This function:
    1. Marks Run as FAILED
    2. Records error message
    3. Triggers cleanup
    """
    from h_arcane.core._internal.infrastructure.events import RunCleanupEvent

    payload = WorkflowFailedEvent.model_validate(ctx.event.data)
    run_id = UUID(payload.run_id)
    error_msg = payload.error

    # Mark run as failed
    async def mark_failed() -> None:
        run = queries.runs.get(run_id)
        if run:
            run.status = RunStatus.FAILED
            run.error_message = error_msg
            run.completed_at = datetime.now(timezone.utc)
            queries.runs.update(run)

    await ctx.step.run("mark-failed", mark_failed)

    # Emit cleanup event
    async def emit_cleanup() -> None:
        event = RunCleanupEvent(
            run_id=str(run_id),
            status="failed",
            error_message=error_msg,
        )
        await inngest_client.send(
            inngest.Event(name=RunCleanupEvent.name, data=event.model_dump())
        )

    await ctx.step.run("emit-cleanup", emit_cleanup)

    return {
        "run_id": str(run_id),
        "status": "failed",
        "error": error_msg,
    }
