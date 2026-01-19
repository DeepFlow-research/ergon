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
