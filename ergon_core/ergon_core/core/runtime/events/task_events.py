"""Task and workflow lifecycle event contracts.

These mirror the ref codebase events but use definition_id instead of experiment_id.
"""

from typing import ClassVar, Literal
from uuid import UUID

from ergon_core.core.runtime.events.base import InngestEventContract

SANDBOX_SKIPPED: Literal["skipped"] = "skipped"
SandboxId = str | Literal["skipped"]


class TaskReadyEvent(InngestEventContract):
    """Emitted when a task's dependencies are satisfied. Triggers task_execute."""

    name: ClassVar[str] = "task/ready"

    run_id: UUID
    definition_id: UUID
    task_id: UUID


class TaskStartedEvent(InngestEventContract):
    """Emitted when task execution begins. Observability only."""

    name: ClassVar[str] = "task/started"

    run_id: UUID
    definition_id: UUID
    task_id: UUID
    execution_id: UUID


class TaskCompletedEvent(InngestEventContract):
    """Emitted when a task completes. Triggers task_propagate + check_evaluators."""

    name: ClassVar[str] = "task/completed"

    run_id: UUID
    definition_id: UUID
    task_id: UUID
    execution_id: UUID
    sandbox_id: SandboxId


class TaskFailedEvent(InngestEventContract):
    """Emitted when a task fails. Triggers task_failure_propagate."""

    name: ClassVar[str] = "task/failed"

    run_id: UUID
    definition_id: UUID
    task_id: UUID
    execution_id: UUID
    error: str
    sandbox_id: SandboxId = SANDBOX_SKIPPED


class WorkflowStartedEvent(InngestEventContract):
    """Emitted to start workflow execution. Triggers workflow_start."""

    name: ClassVar[str] = "workflow/started"

    run_id: UUID
    definition_id: UUID


class WorkflowCompletedEvent(InngestEventContract):
    """Emitted when all tasks complete. Triggers workflow_complete."""

    name: ClassVar[str] = "workflow/completed"

    run_id: UUID
    definition_id: UUID


class WorkflowFailedEvent(InngestEventContract):
    """Emitted when a workflow fails. Triggers workflow_failed."""

    name: ClassVar[str] = "workflow/failed"

    run_id: UUID
    definition_id: UUID
    error: str
