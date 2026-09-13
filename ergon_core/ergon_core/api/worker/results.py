"""Public worker result models."""

from collections.abc import Awaitable, Callable
from time import time
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SpawnedTaskHandle(BaseModel):
    model_config = {"frozen": True}

    task_id: UUID
    waiter: Callable[..., Awaitable["TaskCompletion"]] | None = Field(
        default=None, exclude=True, repr=False
    )

    async def wait(self, *, timeout_seconds: float = 300) -> "TaskCompletion":
        if self.waiter is not None:
            return await self.waiter(self.task_id, timeout_seconds=timeout_seconds)

        raise AwaitCompletionNotSupportedError(
            "SpawnedTaskHandle.wait() requires a handle bound to a WorkerContext."
        )


class AwaitCompletionNotSupportedError(RuntimeError):
    """Raised when a worker tries to synchronously wait for a spawned task."""


class WorkerOutput(BaseModel):
    """Final output of a worker execution."""

    model_config = {"frozen": True}

    output: str
    success: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskCompletion(BaseModel):
    """Native status and full persisted result observed by a bound task handle."""

    task_id: UUID
    status: str
    execution_id: UUID | None = None
    output: WorkerOutput | None = None
    error: str | None = None
    timed_out: bool = False
    checked_at: float = Field(default_factory=time)
    started_at: datetime | None = None
    completed_at: datetime | None = None
