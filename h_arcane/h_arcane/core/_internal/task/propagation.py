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

from h_arcane.core.status import TaskStatus, TaskTrigger
from h_arcane.core._internal.db.queries import queries


# =============================================================================
# State Update Functions
# =============================================================================


def mark_task_ready(
    run_id: UUID,
    task_id: UUID,
    triggered_by: TaskTrigger | None = None,
) -> None:
    """
    Mark a task as READY to execute.

    Records a TaskStateEvent. Current state is derived from event log.

    Args:
        run_id: The run ID
        task_id: The task ID (from task_tree)
        triggered_by: What caused this transition (e.g., TaskTrigger.DEPENDENCY_SATISFIED)
    """
    _update_task_state(run_id, task_id, TaskStatus.READY, triggered_by=triggered_by)


def mark_task_running(
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID | None = None,
) -> None:
    """
    Mark a task as RUNNING.

    Records a TaskStateEvent. Current state is derived from event log.

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
        triggered_by=TaskTrigger.WORKER_STARTED,
    )


def mark_task_completed(
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID | None = None,
) -> None:
    """
    Mark a task as COMPLETED.

    Records a TaskStateEvent. Current state is derived from event log.

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
        triggered_by=TaskTrigger.EXECUTION_SUCCEEDED,
    )


def mark_task_failed(
    run_id: UUID,
    task_id: UUID,
    error: str | None = None,
    execution_id: UUID | None = None,
) -> None:
    """
    Mark a task as FAILED.

    Records a TaskStateEvent. Current state is derived from event log.

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
        triggered_by=TaskTrigger.EXECUTION_FAILED,
        metadata=metadata,
    )


def _update_task_state(
    run_id: UUID,
    task_id: UUID,
    new_status: TaskStatus,
    execution_id: UUID | None = None,
    triggered_by: TaskTrigger | None = None,
    metadata: dict | None = None,
) -> None:
    """
    Internal helper to record task state change to TaskStateEvent.

    Task state is derived from the event log (event sourcing).
    Use queries.task_state_events.get_current_states() to get current state.

    Args:
        run_id: The run ID
        task_id: The task ID
        new_status: The new status to set
        execution_id: The TaskExecution ID (optional)
        triggered_by: What caused this transition
        metadata: Additional metadata for the event
    """
    # Record the state change event (old_status is looked up automatically)
    queries.task_state_events.record_state_change(
        run_id=run_id,
        task_id=task_id,
        new_status=new_status,
        execution_id=execution_id,
        triggered_by=triggered_by,
        metadata=metadata or {},
    )


# =============================================================================
# Dependency Checking
# =============================================================================


def _get_task_tree(run_id: UUID):
    """
    Helper to load and parse the task tree for a run.

    Returns:
        TaskTreeNode or None if not found
    """
    run = queries.runs.get(run_id)
    if run is None:
        return None

    experiment = queries.experiments.get(run.experiment_id)
    if experiment is None:
        return None

    return experiment.parsed_task_tree()


def is_task_ready(run_id: UUID, task_id: UUID) -> bool:
    """
    Check if a task has all its dependencies satisfied.

    A task is ready when:
    1. It has no dependencies, OR
    2. All its dependencies are COMPLETED (checked via TaskStateEvent)

    Args:
        run_id: The run ID
        task_id: The task ID to check

    Returns:
        True if the task can be executed, False otherwise
    """
    tree = _get_task_tree(run_id)
    if tree is None:
        # No tree means no dependencies - task is ready
        return True

    # Get this task's dependencies from the tree
    dependencies = tree.get_dependencies(task_id)
    if not dependencies:
        # No dependencies - task is ready
        return True

    # Check if all dependencies are completed
    task_states = queries.task_state_events.get_current_states(run_id)
    return all(task_states.get(dep_id) == TaskStatus.COMPLETED for dep_id in dependencies)


def get_blocking_dependencies(run_id: UUID, task_id: UUID) -> list[UUID]:
    """
    Get the task IDs that are blocking a task from running.

    Args:
        run_id: The run ID
        task_id: The task to check

    Returns:
        List of task IDs that must complete first
    """
    tree = _get_task_tree(run_id)
    if tree is None:
        return []

    # Get this task's dependencies from the tree
    dependencies = tree.get_dependencies(task_id)
    if not dependencies:
        return []

    # Filter to only non-completed dependencies
    task_states = queries.task_state_events.get_current_states(run_id)
    blocking = [
        dep_id
        for dep_id in dependencies
        if task_states.get(dep_id) != TaskStatus.COMPLETED
    ]
    return blocking


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
    2. Finds tasks that depend on this task (from task_tree)
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

    # 2. Find tasks that depend on this task (from task_tree)
    tree = _get_task_tree(run_id)
    potentially_unblocked: list[UUID] = []
    if tree is not None:
        potentially_unblocked = tree.get_dependents(task_id)

    # 3. Check which tasks are actually ready (all deps satisfied)
    ready_tasks: list[UUID] = []
    for candidate_id in potentially_unblocked:
        if is_task_ready(run_id, candidate_id):
            # Task is ready - update its state
            mark_task_ready(run_id, candidate_id, triggered_by=TaskTrigger.DEPENDENCY_SATISFIED)
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
    tree = experiment.parsed_task_tree()
    if tree is None:
        return False

    # Find the task in the tree to get its parent_id
    task_node = tree.find_by_id(task_id)
    if task_node is None:
        return False

    if task_node.parent_id is None:
        # This is the root task - check if workflow is complete
        return False

    # Get all leaf descendants of the parent (parent_id is UUID)
    parent_node = tree.find_by_id(task_node.parent_id)
    if parent_node is None:
        return False

    leaf_ids = parent_node.get_leaf_ids()

    # Check if all leaf descendants are completed (from event log)
    task_states = queries.task_state_events.get_current_states(run_id)
    all_complete = all(
        task_states.get(leaf_id) == TaskStatus.COMPLETED for leaf_id in leaf_ids
    )

    if all_complete:
        # Mark parent as completed
        # Parent completion doesn't need propagation - it's just state tracking
        parent_uuid = task_node.parent_id
        _update_task_state(
            run_id,
            parent_uuid,
            TaskStatus.COMPLETED,
            execution_id=None,
            triggered_by=TaskTrigger.CHILDREN_COMPLETED,
        )

        # Recursively propagate to grandparent
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
    tree = experiment.parsed_task_tree()
    if tree is None:
        return False

    # Get all leaf tasks using typed method
    all_leaf_ids = tree.get_leaf_ids()

    # Check if all are completed (from event log)
    task_states = queries.task_state_events.get_current_states(run_id)
    return all(task_states.get(leaf_id) == TaskStatus.COMPLETED for leaf_id in all_leaf_ids)


def is_workflow_failed(run_id: UUID) -> bool:
    """
    Check if any task in a workflow has failed.

    Args:
        run_id: The run ID

    Returns:
        True if any task is FAILED, False otherwise
    """
    # Get current states from event log
    task_states = queries.task_state_events.get_current_states(run_id)
    return any(status == TaskStatus.FAILED for status in task_states.values())


# =============================================================================
# Initial Task Computation
# =============================================================================


def get_initial_ready_tasks(run_id: UUID) -> list[UUID]:
    """
    Get tasks that are ready to execute at workflow start.

    These are leaf tasks with no dependencies (or all dependencies already satisfied).

    Args:
        run_id: The run ID

    Returns:
        List of task UUIDs that should be executed first
    """
    tree = _get_task_tree(run_id)
    if tree is None:
        return []

    # Get all leaf tasks using typed method
    all_leaves = tree.get_all_leaves()

    # At workflow start, no tasks are completed yet, so only tasks
    # with no dependencies are ready
    ready_tasks: list[UUID] = []
    for leaf in all_leaves:
        if not leaf.depends_on:
            # No dependencies - task is ready
            ready_tasks.append(leaf.id)

    return ready_tasks
