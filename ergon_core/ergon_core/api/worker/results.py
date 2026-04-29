"""Public worker result models."""

from typing import Any

from pydantic import BaseModel, Field


class WorkerOutput(BaseModel):
    """Final output of a worker execution."""

    model_config = {"frozen": True}

    output: str
    success: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]
