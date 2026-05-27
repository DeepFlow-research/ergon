"""Shared runtime event contracts.

These payloads are emitted by application services and consumed by job-local
Inngest adapters, so their schemas live with the application event boundary
rather than inside any one job package.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal
from uuid import UUID

from ergon_core.core.application.events.base import InngestEventContract


class SampleCancelledEvent(InngestEventContract):
    name: ClassVar[str] = "sample/cancelled"

    sample_id: UUID


class SampleCleanupEvent(InngestEventContract):
    name: ClassVar[str] = "sample/cleanup"

    sample_id: UUID
    status: str
    error_message: str | None = None


class TaskReadyEvent(InngestEventContract):
    name: ClassVar[str] = "task/ready"

    sample_id: UUID
    task_id: UUID


class TaskStartedEvent(InngestEventContract):
    name: ClassVar[str] = "task/started"

    sample_id: UUID
    task_id: UUID
    execution_id: UUID


CancelCause = Literal[
    "manager_decision",
    "parent_terminal",
    "dep_invalidated",
    "downstream_invalidation",
    "run_cancelled",
]
PropagationCancelCause = Literal["parent_terminal", "dep_invalidated"]


class TaskCancelledEvent(InngestEventContract):
    name: ClassVar[str] = "task/cancelled"

    sample_id: UUID
    task_id: UUID
    execution_id: UUID | None
    cause: CancelCause

    model_config = {"frozen": True, "extra": "allow"}


class TaskCompletedEvent(InngestEventContract):
    name: ClassVar[str] = "task/completed"

    sample_id: UUID
    task_id: UUID
    execution_id: UUID
    sandbox_id: str


class TaskFailedEvent(InngestEventContract):
    name: ClassVar[str] = "task/failed"

    sample_id: UUID
    task_id: UUID
    execution_id: UUID
    error: str
    sandbox_id: str | None = None


class WorkflowStartedEvent(InngestEventContract):
    name: ClassVar[str] = "workflow/started"

    sample_id: UUID

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(*args, **kwargs)


class WorkflowCompletedEvent(InngestEventContract):
    name: ClassVar[str] = "workflow/completed"

    sample_id: UUID


class WorkflowFailedEvent(InngestEventContract):
    name: ClassVar[str] = "workflow/failed"

    sample_id: UUID
    error: str
