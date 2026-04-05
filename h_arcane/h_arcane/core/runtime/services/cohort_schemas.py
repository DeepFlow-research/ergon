"""Pydantic DTOs for cohort-facing backend services and APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from h_arcane.core.persistence.telemetry.models import ExperimentCohortStatus
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
    error_message: str | None = None


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
    metadata: dict[str, Any] = Field(default_factory=dict)
