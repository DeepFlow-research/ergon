"""DTOs for experiment definition and launch services."""

from typing import Self
from uuid import UUID

from ergon_core.api.json_types import JsonObject
from pydantic import BaseModel, Field, model_validator


class ExperimentDefineRequest(BaseModel):
    benchmark_slug: str
    name: str | None = None
    cohort_id: UUID | None = None
    limit: int | None = None
    sample_ids: list[str] | None = None
    default_model_target: str | None = None
    default_worker_team: JsonObject = Field(default_factory=dict)
    default_evaluator_slug: str | None = None
    design: JsonObject = Field(default_factory=dict)
    seed: int | None = None
    metadata: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_define_request(self) -> Self:
        if (self.limit is None) == (self.sample_ids is None):
            raise ValueError("Provide exactly one of limit or sample_ids")
        if self.limit is not None and self.limit < 1:
            raise ValueError("limit must be >= 1")

        if self.design.get("arms"):
            raise ValueError("design.arms is not supported until multi-arm launch semantics exist")

        has_default_assignment = bool(self.default_worker_team) and bool(self.default_model_target)
        if not has_default_assignment:
            raise ValueError(
                "Experiment definition requires default_worker_team + default_model_target"
            )
        return self


class ExperimentDefineResult(BaseModel):
    experiment_id: UUID
    cohort_id: UUID | None
    benchmark_type: str
    sample_count: int
    selected_samples: list[str]


class ExperimentRunRequest(BaseModel):
    experiment_id: UUID
    timeout_seconds: int | None = None
    wait: bool = True


class ExperimentRunResult(BaseModel):
    experiment_id: UUID
    run_ids: list[UUID]
    workflow_definition_ids: list[UUID] = Field(default_factory=list)


class RunAssignment(BaseModel):
    instance_key: str
    sample_id: str | None = None
    worker_team: JsonObject
    evaluator_slug: str | None = None
    model_target: str | None = None
    arm_key: str | None = None
    seed: int | None = None
    metadata: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_assignment(self) -> Self:
        if not self.worker_team:
            raise ValueError("Run assignment requires a worker team")
        return self
