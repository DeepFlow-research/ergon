from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ListSamplesCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    limit: int = 20
    status: str | None = None
    definition_id: UUID | None = None
    experiment: str | None = None


class SampleStatusCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    sample_id: UUID


class CancelSampleCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    sample_id: UUID


class SampleSummaryView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    status: str
    created: str
    started: str | None = None
    completed: str | None = None
    duration: str
    definition_id: UUID
    benchmark_type: str
    instance_key: str
    evaluator_slug: str | None = None
    model_target: str | None = None
    error_message: str | None = None


class SampleListResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    samples: tuple[SampleSummaryView, ...]
    status: str | None = None
    definition_id: UUID | None = None
    experiment: str | None = None


class CancelSampleResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    sample: SampleSummaryView
