"""
Task DAG validation - stateless functions for validating task trees.

This module provides pure validation functions that prepare a task tree
for execution by:
1. Flattening the tree (setting parent_id on each task)
2. Resolving dependencies (Task objects → UUIDs)
3. Validating the DAG (no cycles, all deps exist)
4. Computing initial task statuses (which tasks are READY)

All functions mutate the Task objects in place.

Usage:
    from h_arcane.core._internal.task.validation import validate_task_dag

    task = Task(name="Root", children=[a, b, c])
    validate_task_dag(task)  # Raises on validation errors
    # task tree is now ready for serialization
"""

from __future__ import annotations

from uuid import UUID

from h_arcane.core.task import Task, TaskStatus


class TaskValidationError(Exception):
    """Base exception for task validation errors."""

    pass


class CycleDetectedError(TaskValidationError):
    """Raised when a cycle is detected in the task dependency graph."""

    def __init__(self, cycle_path: list[str] | None = None):
        self.cycle_path = cycle_path
        if cycle_path:
            msg = f"Cycle detected in task dependency graph: {' → '.join(cycle_path)}"
        else:
            msg = "Cycle detected in task dependency graph"
        super().__init__(msg)


class MissingDependencyError(TaskValidationError):
    """Raised when a task depends on a non-existent task."""

    def __init__(self, task_name: str, task_id: UUID, missing_dep_id: UUID):
        self.task_name = task_name
        self.task_id = task_id
        self.missing_dep_id = missing_dep_id
        super().__init__(
            f"Task '{task_name}' (id={task_id}) depends on task ID {missing_dep_id} "
            f"which is not in the task tree"
        )


def validate_task_dag(root: Task) -> None:
    """
    Validate and prepare a task tree for execution.

    Performs full DAG processing:
    1. Flatten tree (sets parent_id on each task)
    2. Resolve dependencies (Task → UUID)
    3. Validate DAG (no cycles, deps exist)
    4. Compute initial statuses

    Mutates tasks in place (sets parent_id, _resolved_dependency_ids, status).

    Args:
        root: The root task (may have children)

    Raises:
        CycleDetectedError: If dependency graph contains a cycle
        MissingDependencyError: If a task depends on non-existent task
    """
    tasks = _flatten_tree(root)
    _resolve_dependencies(tasks)
    _validate_no_cycles(tasks)
    _compute_initial_statuses(tasks)


def _flatten_tree(root: Task) -> dict[UUID, Task]:
    """
    Recursively flatten task tree into a mapping.

    Sets parent_id on each task.

    Args:
        root: The root task

    Returns:
        Mapping of task_id → Task for all tasks in the tree
    """
    tasks: dict[UUID, Task] = {}

    def _flatten(task: Task, parent_id: UUID | None) -> None:
        task.parent_id = parent_id
        tasks[task.id] = task
        for child in task.children:
            _flatten(child, parent_id=task.id)

    _flatten(root, parent_id=None)
    return tasks


def _resolve_dependencies(tasks: dict[UUID, Task]) -> None:
    """
    Convert Task object dependencies to UUIDs and validate they exist.

    Populates task._resolved_dependency_ids for each task.

    Args:
        tasks: Mapping of task_id → Task

    Raises:
        MissingDependencyError: If a dependency doesn't exist in tree
    """
    for task in tasks.values():
        resolved_deps: list[UUID] = []

        for dep in task.depends_on:
            if isinstance(dep, Task):
                dep_id = dep.id
            else:
                dep_id = dep  # Already a UUID

            # Validate dependency exists in tree
            if dep_id not in tasks:
                raise MissingDependencyError(
                    task_name=task.name,
                    task_id=task.id,
                    missing_dep_id=dep_id,
                )

            resolved_deps.append(dep_id)

        # Store resolved UUIDs
        task._resolved_dependency_ids = resolved_deps


def _validate_no_cycles(tasks: dict[UUID, Task]) -> None:
    """
    Ensure no cycles in dependency graph using DFS.

    Args:
        tasks: Mapping of task_id → Task

    Raises:
        CycleDetectedError: If a cycle is detected
    """
    visited: set[UUID] = set()
    rec_stack: set[UUID] = set()
    path: list[str] = []

    def has_cycle(task_id: UUID) -> bool:
        """DFS to detect cycles."""
        task = tasks[task_id]
        visited.add(task_id)
        rec_stack.add(task_id)
        path.append(task.name)

        for dep_id in task._resolved_dependency_ids:
            if dep_id not in visited:
                if has_cycle(dep_id):
                    return True
            elif dep_id in rec_stack:
                # Found a cycle - dep is in current recursion stack
                # Try to find the cycle path
                dep_task = tasks[dep_id]
                path.append(dep_task.name)
                return True

        rec_stack.remove(task_id)
        path.pop()
        return False

    for task_id in tasks:
        if task_id not in visited:
            if has_cycle(task_id):
                raise CycleDetectedError(cycle_path=path if path else None)


def _compute_initial_statuses(tasks: dict[UUID, Task]) -> None:
    """
    Mark tasks with no dependencies as READY.

    Only leaf tasks can be READY initially.
    Composite tasks wait for their children.

    Args:
        tasks: Mapping of task_id → Task
    """
    for task in tasks.values():
        # Only leaf tasks can be immediately READY
        if task.is_leaf and not task._resolved_dependency_ids:
            task.status = TaskStatus.READY
        else:
            task.status = TaskStatus.PENDING
