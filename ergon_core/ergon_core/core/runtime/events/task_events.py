"""Task and workflow lifecycle event contracts.

These mirror the ref codebase events but use definition_id instead of experiment_id.
"""

from typing import ClassVar, Literal
from uuid import UUID

from ergon_core.core.runtime.events.base import InngestEventContract

SANDBOX_SKIPPED: Literal["skipped"] = "skipped"
SandboxId = str | Literal["skipped"]

DYNAMIC_TASK_SENTINEL_ID = UUID("00000000-0000-0000-0000-000000000000")


class TaskReadyEvent(InngestEventContract):
    """Emitted when a task's dependencies are satisfied. Triggers task_execute."""

    name: ClassVar[str] = "task/ready"

    run_id: UUID
    definition_id: UUID
    task_id: UUID
    node_id: UUID | None = None


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
    node_id: UUID | None = None


class TaskFailedEvent(InngestEventContract):
    """Emitted when a task fails. Triggers task_failure_propagate."""

    name: ClassVar[str] = "task/failed"

    run_id: UUID
    definition_id: UUID
    task_id: UUID
    execution_id: UUID
    error: str
    sandbox_id: SandboxId = SANDBOX_SKIPPED
    node_id: UUID | None = None


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


# ── Cancel cause ──────────────────────────────────────────────────

CancelCause = Literal[
    "manager_decision",
    "parent_terminal",
    "dep_invalidated",
    "downstream_invalidation",
    "run_cancelled",
]


class TaskCancelledEvent(InngestEventContract):
    """Emitted whenever a node transitions from non-terminal into CANCELLED.

    Consumers:
      - cancel_orphan_subtasks_fn (recurse cascade to descendants)
      - cleanup_cancelled_task_fn (release sandbox, mark execution row)
      - execute_task_fn (via TASK_CANCEL matcher — drops queued / terminates running)
      - dashboard_emitter
    """

    name: ClassVar[str] = "task/cancelled"

    run_id: UUID
    definition_id: UUID
    node_id: UUID
    execution_id: UUID | None
    cause: CancelCause
    sandbox_id: str | None = None  # E2B sandbox_id string; None if task never ran
    benchmark_slug: str | None = None  # benchmark type slug; None if task never ran

    model_config = {"frozen": True, "extra": "allow"}
