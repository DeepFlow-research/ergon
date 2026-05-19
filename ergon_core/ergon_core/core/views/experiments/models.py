"""Experiment API view DTOs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ExperimentStatusCountsDto(BaseModel):
    pending: int = 0
    executing: int = 0
    evaluating: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0


class ExperimentSummaryDto(BaseModel):
    definition_id: UUID
    name: str
    description: str | None = None
    benchmark_type: str
    sample_count: int
    status: str
    default_worker_team: dict = Field(default_factory=dict)
    default_evaluator_slug: str | None = None
    default_model_target: str | None = None
    created_by: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    run_count: int = 0


class ExperimentRunRowDto(BaseModel):
    run_id: UUID
    definition_id: UUID
    benchmark_type: str
    instance_key: str
    status: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    evaluator_slug: str | None = None
    model_target: str | None = None
    worker_team: dict = Field(default_factory=dict)
    seed: int | None = None
    running_time_ms: int | None = None
    final_score: float | None = None
    total_tasks: int | None = None
    total_cost_usd: float | None = None
    error_message: str | None = None


class ExperimentAnalyticsDto(BaseModel):
    total_runs: int = 0
    status_counts: ExperimentStatusCountsDto = Field(default_factory=ExperimentStatusCountsDto)
    average_score: float | None = None
    average_duration_ms: int | None = None
    average_tasks: float | None = None
    total_cost_usd: float | None = None
    latest_activity_at: datetime | None = None
    error_count: int = 0


class ExperimentDetailDto(BaseModel):
    # Kept denormalized so the public contract exposes definition identity and
    # display fields without requiring consumers to traverse the nested summary.
    definition_id: UUID | None = None
    name: str | None = None
    description: str | None = None
    benchmark_type: str | None = None
    experiment: ExperimentSummaryDto
    runs: list[ExperimentRunRowDto] = Field(default_factory=list)
    analytics: ExperimentAnalyticsDto = Field(default_factory=ExperimentAnalyticsDto)
    sample_selection: dict = Field(default_factory=dict)
    design: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _backfill_identity_from_summary(self) -> "ExperimentDetailDto":
        if self.definition_id is None:
            self.definition_id = self.experiment.definition_id
        if self.name is None:
            self.name = self.experiment.name
        if self.description is None:
            self.description = self.experiment.description
        if self.benchmark_type is None:
            self.benchmark_type = self.experiment.benchmark_type
        return self
