"""Public worker result models."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SpawnedTaskHandle(BaseModel):
    model_config = {"frozen": True}

    task_id: UUID

    async def wait(self) -> None:
        raise AwaitCompletionNotSupportedError(
            "SpawnedTaskHandle.wait() is deferred in v2; spawned tasks run asynchronously."
        )


class AwaitCompletionNotSupportedError(RuntimeError):
    """Raised when a worker tries to synchronously wait for a spawned task."""


class WorkerOutput(BaseModel):
    """Final output of a worker execution."""

    model_config = {"frozen": True}

    output: str
    success: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]
