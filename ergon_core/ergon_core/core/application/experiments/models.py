"""DTOs for experiment launch services."""

from typing import Self
from uuid import UUID

from ergon_core.core.shared.json_types import JsonObject
from pydantic import BaseModel, Field, model_validator


class ExperimentRunRequest(BaseModel):
    definition_id: UUID
    timeout_seconds: int | None = None
    wait: bool = True


class ExperimentRunResult(BaseModel):
    definition_id: UUID
    run_ids: list[UUID]
    workflow_definition_ids: list[UUID] = Field(default_factory=list)


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
