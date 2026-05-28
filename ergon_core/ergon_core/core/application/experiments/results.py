"""Experiment application result models shared with the public API."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, JsonValue


class PersistedExperiment(BaseModel):
    experiment_id: UUID
    name: str
    environment_ids: Mapping[str, UUID] = Field(default_factory=dict)
    created_at: datetime | None = None
    dashboard_url: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class ExperimentSubmitResult(BaseModel):
    experiment_id: UUID
    sampler_invocation_id: UUID | None = None
    batch_id: UUID | None = None
    requested_k: int
    candidate_pool_size: int
    selected_count: int
    sample_ids: Sequence[UUID]
    dashboard_url: str | None = None
