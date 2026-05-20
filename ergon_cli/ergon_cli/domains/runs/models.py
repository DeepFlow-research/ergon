from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ListRunsCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    limit: int = 20
    status: str | None = None
    definition_id: UUID | None = None
    experiment: str | None = None


class RunStatusCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: UUID


class CancelRunCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: UUID


class RunSummaryView(BaseModel):
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


class RunListResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    runs: tuple[RunSummaryView, ...]
    status: str | None = None
    definition_id: UUID | None = None
    experiment: str | None = None


class CancelRunResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    run: RunSummaryView
