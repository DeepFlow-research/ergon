"""Public worker result models."""

from pydantic import BaseModel, Field
from ergon_core.core.shared.json_types import JsonObject


class WorkerOutput(BaseModel):
    """Final output of a worker execution."""

    model_config = {"frozen": True}

    output: str
    success: bool = True
    metadata: JsonObject = Field(default_factory=dict)
