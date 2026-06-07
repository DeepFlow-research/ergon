"""DTOs and public contracts for experiment services."""

from typing import Self

from ergon_core.core.shared.json_types import JsonObject
from pydantic import BaseModel, Field, model_validator


class SampleAssignment(BaseModel):
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
