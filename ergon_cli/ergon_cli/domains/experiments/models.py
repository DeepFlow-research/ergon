from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ListExperimentsCommand(BaseModel):
    model_config = ConfigDict(frozen=True)
    limit: int = 50


class ShowExperimentCommand(BaseModel):
    model_config = ConfigDict(frozen=True)
    definition_id: UUID


class ListTagsCommand(BaseModel):
    model_config = ConfigDict(frozen=True)


class ListByTagCommand(BaseModel):
    model_config = ConfigDict(frozen=True)
    tag: str


class ExperimentSummaryView(BaseModel):
    model_config = ConfigDict(frozen=True)

    definition_id: UUID
    name: str
    benchmark_type: str
    status: str
    sample_count: int
    run_count: int
    default_model_target: str | None = None
    default_evaluator_slug: str | None = None


class ExperimentRunView(BaseModel):
    model_config = ConfigDict(frozen=True)

    sample_id: UUID
    instance_key: str
    status: str
    model_target: str | None = None


class ExperimentDetailView(BaseModel):
    model_config = ConfigDict(frozen=True)

    experiment: ExperimentSummaryView
    sample_selection: dict
    runs: tuple[ExperimentRunView, ...]


class ExperimentTagDefinitionView(BaseModel):
    model_config = ConfigDict(frozen=True)

    definition_id: UUID
    name: str
    benchmark_type: str
    latest_run_status: str | None = None
