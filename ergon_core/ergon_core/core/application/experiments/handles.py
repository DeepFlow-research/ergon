"""Core lifecycle handles for persisted workflow definitions."""

from datetime import datetime
from typing import Any
from uuid import UUID

from ergon_core.core.shared.utils import utcnow
from pydantic import BaseModel, Field


class DefinitionHandle(BaseModel):
    """Rich handle returned after a benchmark definition is persisted."""

    model_config = {"frozen": True}

    definition_id: UUID
    benchmark_type: str
    worker_bindings: dict[str, str] = Field(default_factory=dict)
    evaluator_bindings: dict[str, str] = Field(default_factory=dict)
    instance_count: int = 0
    task_count: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]
