"""Pydantic DTOs for cohort-facing backend services and APIs."""

from datetime import datetime
from uuid import UUID

from ergon_core.api.json_types import JsonObject
from ergon_core.core.persistence.telemetry.models import ExperimentCohortStatus
from pydantic import BaseModel, Field


class CohortStatusCountsDto(BaseModel):
    """Aggregate run counts by lifecycle status."""

    pending: int = 0
    executing: int = 0
    evaluating: int = 0
    completed: int = 0
    failed: int = 0


class CohortSummaryDto(BaseModel):
    """Summary row for cohort list and live updates."""

    cohort_id: UUID
    name: str
    description: str | None = None
    created_by: str | None = None
    created_at: datetime
    status: str
    total_runs: int = 0
    status_counts: CohortStatusCountsDto = Field(default_factory=CohortStatusCountsDto)
    average_score: float | None = None
    best_score: float | None = None
    worst_score: float | None = None
    average_duration_ms: int | None = None
    failure_rate: float = 0.0
    stats_updated_at: datetime | None = None


class CohortExperimentRowDto(BaseModel):
    """One experiment inside a cohort detail view."""

    experiment_id: UUID
    name: str
    benchmark_type: str
    sample_count: int
    total_runs: int = 0
    status_counts: CohortStatusCountsDto = Field(default_factory=CohortStatusCountsDto)
    status: str
    created_at: datetime
    default_model_target: str | None = None
    default_evaluator_slug: str | None = None
    final_score: float | None = None
    total_cost_usd: float | None = None
    error_message: str | None = None


class CohortDetailDto(BaseModel):
    """Full payload for a single cohort detail page."""

    summary: CohortSummaryDto
    experiments: list[CohortExperimentRowDto] = Field(default_factory=list)


class UpdateCohortRequest(BaseModel):
    """Mutable cohort fields exposed through the operator API."""

    status: ExperimentCohortStatus


class ResolveCohortRequest(BaseModel):
    """Request to resolve or create a cohort by name."""

    name: str
    description: str | None = None
    created_by: str | None = None
    metadata: JsonObject = Field(default_factory=dict)
