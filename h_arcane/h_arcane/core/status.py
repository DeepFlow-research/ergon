"""Core enums for h_arcane.

Separated to avoid circular imports between task.py and models.py.
"""

from enum import Enum


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"  # Not ready (dependencies not met)
    READY = "ready"  # Dependencies satisfied, waiting for execution
    RUNNING = "running"  # Currently executing
    COMPLETED = "completed"  # Successfully finished
    FAILED = "failed"  # Execution failed


class TaskTrigger(str, Enum):
    """What triggered a task state transition."""

    WORKFLOW_STARTED = "workflow_started"  # Initial task states when workflow begins
    DEPENDENCY_SATISFIED = "dependency_satisfied"  # Task becomes ready after dependencies complete
    WORKER_STARTED = "worker_started"  # Task transitions to running
    EXECUTION_SUCCEEDED = "execution_succeeded"  # Task completed successfully
    EXECUTION_FAILED = "execution_failed"  # Task failed
    CHILDREN_COMPLETED = "children_completed"  # Parent task completes after children
