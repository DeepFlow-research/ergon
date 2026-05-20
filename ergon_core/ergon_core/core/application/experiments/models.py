"""DTOs and public contracts for experiment services."""

from datetime import datetime
from typing import Any
from typing import Self
from uuid import UUID

from ergon_core.core.shared.json_types import JsonObject
from ergon_core.core.shared.utils import utcnow
from pydantic import BaseModel, Field, model_validator


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


class ExperimentRunRequest(BaseModel):
    definition_id: UUID
    timeout_seconds: int | None = None
    wait: bool = True


class ExperimentRunResult(BaseModel):
    definition_id: UUID
    run_ids: list[UUID]
    definition_ids: list[UUID] = Field(default_factory=list)


class RunAssignment(BaseModel):
    instance_key: str
    sample_id: str | None = None
    worker_team: JsonObject
    evaluator_slug: str | None = None
    evaluator_bindings: dict[str, str] = Field(default_factory=dict)
    model_target: str | None = None
    sandbox_slug: str | None = None
    dependency_extras: tuple[str, ...] = ()
    arm_key: str | None = None
    seed: int | None = None
    metadata: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_assignment(self) -> Self:
        if not self.worker_team:
            raise ValueError("Run assignment requires a worker team")
        return self
