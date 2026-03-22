"""
In-memory worker context for task execution.

This module provides a simple mapping from task_id -> worker instance.
Since execute_task() and worker_execute() run in the same process (the container),
we can store worker references in memory rather than serializing them.

Usage:
    # When task is created/registered (in execute_task)
    from h_arcane.core._internal.task.worker_context import store_worker
    store_worker(task.id, task.assigned_to)

    # When worker needs to execute (in worker_execute)
    from h_arcane.core._internal.task.worker_context import get_worker
    worker = get_worker(task_id)
    result = await worker.execute(...)
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from h_arcane.core._internal.task.schema import TaskTreeNode
    from h_arcane.core.worker import BaseWorker
    from h_arcane.core.task import Task

# In-memory store: task_id -> worker instance
_TASK_WORKERS: dict[UUID, "BaseWorker"] = {}


def store_worker(task_id: UUID, worker: "BaseWorker") -> None:
    """
    Store a worker instance for a task.

    Called during task registration to associate a worker with a task.

    Args:
        task_id: The task's UUID
        worker: The worker instance to store
    """
    _TASK_WORKERS[task_id] = worker


def get_worker(task_id: UUID) -> "BaseWorker":
    """
    Get the worker instance for a task.

    Called during task execution to retrieve the worker.

    Args:
        task_id: The task's UUID

    Returns:
        The worker instance

    Raises:
        KeyError: If no worker is registered for this task
    """
    if task_id not in _TASK_WORKERS:
        raise KeyError(
            f"No worker registered for task {task_id}. "
            "Make sure the task was created with assigned_to and registered via execute_task()."
        )
    return _TASK_WORKERS[task_id]


def clear_worker(task_id: UUID) -> None:
    """
    Remove a worker from the store.

    Called after task execution to clean up.

    Args:
        task_id: The task's UUID
    """
    _TASK_WORKERS.pop(task_id, None)


def clear_all_workers() -> None:
    """Clear all stored workers. Useful for testing."""
    _TASK_WORKERS.clear()


def store_workers_from_task(task: "Task") -> None:
    """
    Recursively store workers for a task and all its descendants.

    Args:
        task: The root task (may have children)
    """

    # Store worker for this task
    if task.assigned_to:
        store_worker(task.id, task.assigned_to)

    # Recursively store for children
    for child in task.children:
        store_workers_from_task(child)


def clear_workers_from_task(task: "Task") -> None:
    """Recursively clear workers for a task tree."""
    clear_worker(task.id)
    for child in task.children:
        clear_workers_from_task(child)


def store_worker_for_tree(task_tree: "TaskTreeNode", worker: "BaseWorker") -> None:
    """Register one reconstructed worker instance for every node in a stored task tree."""
    for node in task_tree.walk():
        store_worker(node.id, worker)
