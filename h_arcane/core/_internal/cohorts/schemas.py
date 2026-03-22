"""Pydantic schemas for cohort-facing backend services and APIs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.core._internal.db.models import (
    CohortMetadata,
    CohortStatsExtras,
    DispatchConfigSnapshot,
    ExperimentCohortStatus,
    RunStatus,
    SandboxConfigSnapshot,
)


class CohortStatusCountsDto(BaseModel):
    """Aggregate run counts by lifecycle status."""

    pending: int = 0
    executing: int = 0
    evaluating: int = 0
    completed: int = 0
    failed: int = 0


class CohortMetadataSummaryDto(BaseModel):
    """Typed reproducibility metadata exposed to the frontend."""

    code_commit_sha: str | None = None
    repo_dirty: bool | None = None
    prompt_version: str | None = None
    worker_version: str | None = None
    model_provider: str | None = None
    model_name: str | None = None
    sandbox_config: SandboxConfigSnapshot = Field(default_factory=SandboxConfigSnapshot)
    dispatch_config: DispatchConfigSnapshot = Field(default_factory=DispatchConfigSnapshot)

    @classmethod
    def from_model(cls, metadata: CohortMetadata) -> "CohortMetadataSummaryDto":
        """Convert persisted cohort metadata to API DTO form."""
        return cls.model_validate(metadata.model_dump())


class CohortSummaryDto(BaseModel):
    """Summary row for cohort list and live updates."""

    cohort_id: UUID
    name: str
    description: str | None = None
    created_by: str | None = None
    created_at: datetime
    status: ExperimentCohortStatus
    total_runs: int = 0
    status_counts: CohortStatusCountsDto = Field(default_factory=CohortStatusCountsDto)
    average_score: float | None = None
    best_score: float | None = None
    worst_score: float | None = None
    average_duration_ms: int | None = None
    failure_rate: float = 0.0
    metadata_summary: CohortMetadataSummaryDto = Field(default_factory=CohortMetadataSummaryDto)
    stats_updated_at: datetime | None = None
    extras: CohortStatsExtras = Field(default_factory=CohortStatsExtras)


class UpdateCohortRequest(BaseModel):
    """Mutable cohort fields exposed through the operator API."""

    status: ExperimentCohortStatus


class CohortRunRowDto(BaseModel):
    """A frontend-facing row describing one run inside a cohort."""

    run_id: UUID
    experiment_id: UUID
    benchmark_name: BenchmarkName
    experiment_task_id: str
    workflow_name: str
    cohort_id: UUID
    cohort_name: str
    status: RunStatus
    worker_model: str
    max_questions: int
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    running_time_ms: int | None = None
    final_score: float | None = None
    normalized_score: float | None = None
    error_message: str | None = None


class CohortDetailDto(BaseModel):
    """Full frontend payload for a single cohort detail page."""

    summary: CohortSummaryDto
    runs: list[CohortRunRowDto] = Field(default_factory=list)


class ResolveCohortRequest(BaseModel):
    """Request to resolve or create a cohort by compulsory name."""

    name: str
    description: str | None = None
    created_by: str | None = None
    metadata: CohortMetadata = Field(default_factory=CohortMetadata)
