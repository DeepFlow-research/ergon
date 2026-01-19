"""
DAG Propagation Logic - Pure functions for task state management.

This module contains the core DAG execution logic. All functions operate
on the database and return information needed by the orchestration layer
(Inngest functions) to emit events.

Key concepts:
- A task can be "ready" when all its dependencies are satisfied
- When a task completes, we check what tasks are now unblocked
- Composite tasks (with children) complete when all leaf descendants complete
- State transitions are logged to TaskStateEvent for audit/replay

Usage:
    from h_arcane.core._internal.task.propagation import on_task_completed

    # When a task finishes executing:
    ready_tasks = on_task_completed(run_id, task_id, execution_id)

    # ready_tasks is a list of task_ids that should now be executed
"""

from __future__ import annotations

from uuid import UUID

from h_arcane.core.task import TaskStatus
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.task.schema import parse_task_tree


# =============================================================================
# State Update Functions
# =============================================================================


def mark_task_ready(
    run_id: UUID,
    task_id: UUID,
    triggered_by: str | None = None,
) -> None:
    """
    Mark a task as READY to execute.

    Updates Run.task_states and records a TaskStateEvent.

    Args:
        run_id: The run ID
        task_id: The task ID (from task_tree)
        triggered_by: What caused this transition (e.g., "dependency_satisfied")
    """
    _update_task_state(run_id, task_id, TaskStatus.READY, triggered_by=triggered_by)


def mark_task_running(
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID | None = None,
) -> None:
    """
    Mark a task as RUNNING.

    Updates Run.task_states and records a TaskStateEvent.

    Args:
        run_id: The run ID
        task_id: The task ID
        execution_id: The TaskExecution ID (if any)
    """
    _update_task_state(
        run_id,
        task_id,
        TaskStatus.RUNNING,
        execution_id=execution_id,
        triggered_by="worker_started",
    )


def mark_task_completed(
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID | None = None,
) -> None:
    """
    Mark a task as COMPLETED.

    Updates Run.task_states and records a TaskStateEvent.

    Args:
        run_id: The run ID
        task_id: The task ID
        execution_id: The TaskExecution ID (if any)
    """
    _update_task_state(
        run_id,
        task_id,
        TaskStatus.COMPLETED,
        execution_id=execution_id,
        triggered_by="execution_succeeded",
    )


def mark_task_failed(
    run_id: UUID,
    task_id: UUID,
    error: str | None = None,
    execution_id: UUID | None = None,
) -> None:
    """
    Mark a task as FAILED.

    Updates Run.task_states and records a TaskStateEvent.

    Args:
        run_id: The run ID
        task_id: The task ID
        error: Error message (stored in event metadata)
        execution_id: The TaskExecution ID (if any)
    """
    metadata = {"error": error} if error else {}
    _update_task_state(
        run_id,
        task_id,
        TaskStatus.FAILED,
        execution_id=execution_id,
        triggered_by="execution_failed",
        metadata=metadata,
    )


def _update_task_state(
    run_id: UUID,
    task_id: UUID,
    new_status: TaskStatus,
    execution_id: UUID | None = None,
    triggered_by: str | None = None,
    metadata: dict | None = None,
) -> None:
    """
    Internal helper to update task state in Run and log to TaskStateEvent.

    Uses atomic update to ensure consistency between Run.task_states and TaskStateEvent.

    Args:
        run_id: The run ID
        task_id: The task ID
        new_status: The new status to set
        execution_id: The TaskExecution ID (optional)
        triggered_by: What caused this transition
        metadata: Additional metadata for the event
    """
    # Get current run and state to determine old_status
    run = queries.runs.get(run_id)
    if run is None:
        raise ValueError(f"Run {run_id} not found")

    task_states = run.task_states or {}
    old_status = task_states.get(str(task_id))

    # Atomically update both Run.task_states and TaskStateEvent
    queries.task_state_events.update_task_state_atomic(
        run_id=run_id,
        task_id=task_id,
        new_status=new_status.value,
        old_status=old_status,
        execution_id=execution_id,
        triggered_by=triggered_by,
        metadata=metadata or {},
    )


# =============================================================================
# Dependency Checking
# =============================================================================


def is_task_ready(run_id: UUID, task_id: UUID) -> bool:
    """
    Check if a task has all its dependencies satisfied.

    A task is ready when:
    1. It has no dependencies, OR
    2. All its dependencies are satisfied (marked in TaskDependency table)

    Args:
        run_id: The run ID
        task_id: The task ID to check

    Returns:
        True if the task can be executed, False otherwise
    """
    return queries.task_dependencies.is_task_unblocked(run_id, task_id)


def get_blocking_dependencies(run_id: UUID, task_id: UUID) -> list[UUID]:
    """
    Get the task IDs that are blocking a task from running.

    Args:
        run_id: The run ID
        task_id: The task to check

    Returns:
        List of task IDs that must complete first
    """
    blocking = queries.task_dependencies.get_blocking(run_id, task_id)
    return [dep.dependency_task_id for dep in blocking]


# =============================================================================
# Completion Propagation
# =============================================================================


def on_task_completed(
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID,
) -> list[UUID]:
    """
    Handle task completion - the core propagation function.

    This function:
    1. Marks the task as COMPLETED (state + event)
    2. Marks dependencies on this task as satisfied
    3. Checks which dependent tasks are now unblocked
    4. Propagates completion to parent composite tasks (if applicable)

    Args:
        run_id: The run ID
        task_id: The task that completed
        execution_id: The TaskExecution ID

    Returns:
        List of task_ids that are now ready to execute
    """
    # 1. Mark this task as completed
    mark_task_completed(run_id, task_id, execution_id)

    # 2. Mark dependencies as satisfied and get potentially unblocked tasks
    potentially_unblocked = queries.task_dependencies.mark_satisfied(
        run_id=run_id,
        dependency_task_id=task_id,
        execution_id=execution_id,
    )

    # 3. Check which tasks are actually ready (all deps satisfied)
    ready_tasks: list[UUID] = []
    for candidate_id in potentially_unblocked:
        if is_task_ready(run_id, candidate_id):
            # Task is ready - update its state
            mark_task_ready(run_id, candidate_id, triggered_by="dependency_satisfied")
            ready_tasks.append(candidate_id)

    # 4. Propagate to parent composite tasks
    propagate_to_parent(run_id, task_id)

    return ready_tasks


def propagate_to_parent(run_id: UUID, task_id: UUID) -> bool:
    """
    Check if parent composite should be marked complete.

    When a leaf task completes, we check if all siblings under the
    parent composite are also complete. If so, the parent is marked
    complete and we recursively check its parent.

    Args:
        run_id: The run ID
        task_id: The task that completed

    Returns:
        True if a parent was marked complete, False otherwise
    """
    # Get the task_tree from the experiment
    run = queries.runs.get(run_id)
    if run is None:
        return False

    experiment = queries.experiments.get(run.experiment_id)
    if experiment is None:
        return False

    # Parse task_tree into typed model
    tree = parse_task_tree(experiment.task_tree)
    if tree is None:
        return False

    # Find the task in the tree to get its parent_id
    task_node = tree.find_by_id(str(task_id))
    if task_node is None:
        return False

    if task_node.parent_id is None:
        # This is the root task - check if workflow is complete
        return False

    # Get all leaf descendants of the parent
    parent_node = tree.find_by_id(task_node.parent_id)
    if parent_node is None:
        return False

    leaf_ids = parent_node.get_leaf_ids()

    # Check if all leaf descendants are completed
    task_states = run.task_states or {}
    all_complete = all(
        task_states.get(leaf_id) == TaskStatus.COMPLETED.value for leaf_id in leaf_ids
    )

    if all_complete:
        # Mark parent as completed WITHOUT emitting event
        # Parent completion doesn't need propagation - it's just state tracking
        parent_uuid = UUID(task_node.parent_id)
        _update_task_state(
            run_id,
            parent_uuid,
            TaskStatus.COMPLETED,
            execution_id=None,
            triggered_by="children_completed",
        )

        # Recursively propagate to grandparent (also without emitting events)
        propagate_to_parent(run_id, parent_uuid)
        return True

    return False


# =============================================================================
# Tree Traversal Helpers
# =============================================================================


def get_root_task_id(run_id: UUID) -> UUID | None:
    """
    Get the root task ID for a run.

    Args:
        run_id: The run ID

    Returns:
        The root task UUID, or None if not found
    """
    run = queries.runs.get(run_id)
    if run is None:
        return None

    experiment = queries.experiments.get(run.experiment_id)
    if experiment is None or not experiment.root_task_id:
        return None

    return UUID(experiment.root_task_id)


def is_workflow_complete(run_id: UUID) -> bool:
    """
    Check if all tasks in a workflow are complete.

    Args:
        run_id: The run ID

    Returns:
        True if all tasks are COMPLETED, False otherwise
    """
    run = queries.runs.get(run_id)
    if run is None:
        return False

    experiment = queries.experiments.get(run.experiment_id)
    if experiment is None:
        return False

    # Parse task_tree into typed model
    tree = parse_task_tree(experiment.task_tree)
    if tree is None:
        return False

    # Get all leaf tasks using typed method
    all_leaf_ids = tree.get_leaf_ids()

    # Check if all are completed
    task_states = run.task_states or {}
    return all(task_states.get(leaf_id) == TaskStatus.COMPLETED.value for leaf_id in all_leaf_ids)


def is_workflow_failed(run_id: UUID) -> bool:
    """
    Check if any task in a workflow has failed.

    Args:
        run_id: The run ID

    Returns:
        True if any task is FAILED, False otherwise
    """
    run = queries.runs.get(run_id)
    if run is None:
        return False

    task_states = run.task_states or {}
    return any(status == TaskStatus.FAILED.value for status in task_states.values())


# =============================================================================
# Initial Task Computation
# =============================================================================


def get_initial_ready_tasks(run_id: UUID) -> list[UUID]:
    """
    Get tasks that are ready to execute at workflow start.

    These are leaf tasks with no dependencies.

    Args:
        run_id: The run ID

    Returns:
        List of task UUIDs that should be executed first
    """
    run = queries.runs.get(run_id)
    if run is None:
        return []

    experiment = queries.experiments.get(run.experiment_id)
    if experiment is None:
        return []

    # Parse task_tree into typed model
    tree = parse_task_tree(experiment.task_tree)
    if tree is None:
        return []

    # Get all leaf tasks using typed method
    all_leaf_ids = tree.get_leaf_ids()

    # Find those with no dependencies
    ready_tasks: list[UUID] = []
    for leaf_id_str in all_leaf_ids:
        leaf_id = UUID(leaf_id_str)

        # Check if this task has any dependencies
        if is_task_ready(run_id, leaf_id):
            ready_tasks.append(leaf_id)

    return ready_tasks
