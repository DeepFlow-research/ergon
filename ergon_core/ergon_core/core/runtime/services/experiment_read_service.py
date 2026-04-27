"""Read service for experiment API views."""

from datetime import datetime
from uuid import UUID

from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import ExperimentRecord, RunRecord
from pydantic import BaseModel, Field
from sqlmodel import select


class ExperimentSummaryDto(BaseModel):
    experiment_id: UUID
    cohort_id: UUID | None = None
    name: str
    benchmark_type: str
    sample_count: int
    status: str
    default_worker_team: dict = Field(default_factory=dict)
    default_evaluator_slug: str | None = None
    default_model_target: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    run_count: int = 0


class ExperimentRunRowDto(BaseModel):
    run_id: UUID
    workflow_definition_id: UUID
    benchmark_type: str
    instance_key: str
    status: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    evaluator_slug: str | None = None
    model_target: str | None = None


class ExperimentDetailDto(BaseModel):
    experiment: ExperimentSummaryDto
    runs: list[ExperimentRunRowDto] = Field(default_factory=list)
    sample_selection: dict = Field(default_factory=dict)
    design: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class ExperimentReadService:
    def list_experiments(self, *, limit: int = 50) -> list[ExperimentSummaryDto]:
        with get_session() as session:
            experiments = list(
                session.exec(
                    select(ExperimentRecord)
                    .order_by(ExperimentRecord.created_at.desc())
                    .limit(limit)
                ).all()
            )
            return [_summary(session, experiment) for experiment in experiments]

    def get_experiment(self, experiment_id: UUID) -> ExperimentDetailDto | None:
        with get_session() as session:
            experiment = session.get(ExperimentRecord, experiment_id)
            if experiment is None:
                return None
            runs = list(
                session.exec(
                    select(RunRecord).where(RunRecord.experiment_id == experiment.id)
                ).all()
            )
            return ExperimentDetailDto(
                experiment=_summary(session, experiment, runs=runs),
                runs=[_run_row(run) for run in runs],
                sample_selection=experiment.parsed_sample_selection(),
                design=experiment.parsed_design(),
                metadata=experiment.parsed_metadata(),
            )


def _summary(
    session,
    experiment: ExperimentRecord,
    *,
    runs: list[RunRecord] | None = None,
) -> ExperimentSummaryDto:
    run_count = len(runs) if runs is not None else _run_count(session, experiment.id)
    return ExperimentSummaryDto(
        experiment_id=experiment.id,
        cohort_id=experiment.cohort_id,
        name=experiment.name,
        benchmark_type=experiment.benchmark_type,
        sample_count=experiment.sample_count,
        status=experiment.status,
        default_worker_team=experiment.parsed_default_worker_team(),
        default_evaluator_slug=experiment.default_evaluator_slug,
        default_model_target=experiment.default_model_target,
        created_at=experiment.created_at,
        started_at=experiment.started_at,
        completed_at=experiment.completed_at,
        run_count=run_count,
    )


def _run_count(session, experiment_id: UUID) -> int:
    return len(
        list(session.exec(select(RunRecord.id).where(RunRecord.experiment_id == experiment_id)))
    )


def _run_row(run: RunRecord) -> ExperimentRunRowDto:
    return ExperimentRunRowDto(
        run_id=run.id,
        workflow_definition_id=run.workflow_definition_id,
        benchmark_type=run.benchmark_type,
        instance_key=run.instance_key,
        status=run.status,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        evaluator_slug=run.evaluator_slug,
        model_target=run.model_target,
    )
