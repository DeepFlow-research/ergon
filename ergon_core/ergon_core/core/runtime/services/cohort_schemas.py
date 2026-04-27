"""Pydantic DTOs for cohort-facing backend services and APIs."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from ergon_core.api.json_types import JsonObject
from ergon_core.core.persistence.telemetry.models import ExperimentCohortStatus
from pydantic import BaseModel, Field

RubricStatusSummaryStatus = Literal["passing", "failing", "errored", "skipped", "mixed", "none"]


class CohortStatusCountsDto(BaseModel):
    """Aggregate run counts by lifecycle status."""

    pending: int = 0
    executing: int = 0
    evaluating: int = 0
    completed: int = 0
    failed: int = 0


class CohortRubricStatusSummaryDto(BaseModel):
    """Backend-owned rubric status summary for one cohort run row."""

    status: RubricStatusSummaryStatus
    total_criteria: int
    passed: int
    failed: int
    errored: int
    skipped: int
    criterion_statuses: list[str]
    evaluator_names: list[str]


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


class CohortRunRowDto(BaseModel):
    """One run inside a cohort detail view."""

    run_id: UUID
    definition_id: UUID
    cohort_id: UUID
    cohort_name: str
    status: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    running_time_ms: int | None = None
    final_score: float | None = None
    total_tasks: int | None = None
    total_cost_usd: float | None = None
    error_message: str | None = None
    rubric_status_summary: CohortRubricStatusSummaryDto


class CohortDetailDto(BaseModel):
    """Full payload for a single cohort detail page."""

    summary: CohortSummaryDto
    runs: list[CohortRunRowDto] = Field(default_factory=list)


class UpdateCohortRequest(BaseModel):
    """Mutable cohort fields exposed through the operator API."""

    status: ExperimentCohortStatus


class ResolveCohortRequest(BaseModel):
    """Request to resolve or create a cohort by name."""

    name: str
    description: str | None = None
    created_by: str | None = None
    metadata: JsonObject = Field(default_factory=dict)
