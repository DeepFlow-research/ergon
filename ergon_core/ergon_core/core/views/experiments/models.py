"""Experiment API view DTOs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)


class SamplerInvocationView(CamelModel):
    sampler_invocation_id: UUID
    sampler_name: str
    requested_k: int
    candidate_pool_size: int
    selected_count: int
    sampler_config: dict = Field(default_factory=dict)
    created_at: datetime


class EnvironmentContributionView(CamelModel):
    environment_id: UUID
    environment_name: str
    source_mode: str
    sample_count: int
    selected_count: int
    source_metadata: dict = Field(default_factory=dict)


class ExperimentSampleSummaryView(CamelModel):
    sample_id: UUID
    experiment_id: UUID
    environment_id: UUID
    environment_name: str
    sample_key: str
    sample_ref: dict = Field(default_factory=dict)
    source_metadata: dict = Field(default_factory=dict)
    status: str
    created_at: datetime


class ExperimentDetailView(CamelModel):
    experiment_id: UUID
    name: str
    description: str | None = None
    environments: list[EnvironmentContributionView] = Field(default_factory=list)
    sample_count: int
    samples: list[ExperimentSampleSummaryView] = Field(default_factory=list)
    sampler_invocations: list[SamplerInvocationView] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime


class ExperimentListView(CamelModel):
    items: list[ExperimentDetailView] = Field(default_factory=list)


class ExperimentSamplesView(CamelModel):
    items: list[ExperimentSampleSummaryView] = Field(default_factory=list)


class SamplerInvocationsView(CamelModel):
    items: list[SamplerInvocationView] = Field(default_factory=list)
