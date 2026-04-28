"""Read service for experiment API views."""

from datetime import datetime
from uuid import UUID

from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import ExperimentRecord, RunRecord
from pydantic import BaseModel, Field
from sqlmodel import select


class ExperimentStatusCountsDto(BaseModel):
    pending: int = 0
    executing: int = 0
    evaluating: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0


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
    worker_team: dict = Field(default_factory=dict)
    seed: int | None = None
    running_time_ms: int | None = None
    final_score: float | None = None
    total_tasks: int | None = None
    total_cost_usd: float | None = None
    error_message: str | None = None


class ExperimentAnalyticsDto(BaseModel):
    total_runs: int = 0
    status_counts: ExperimentStatusCountsDto = Field(default_factory=ExperimentStatusCountsDto)
    average_score: float | None = None
    average_duration_ms: int | None = None
    average_tasks: float | None = None
    total_cost_usd: float | None = None
    latest_activity_at: datetime | None = None
    error_count: int = 0


class ExperimentDetailDto(BaseModel):
    experiment: ExperimentSummaryDto
    runs: list[ExperimentRunRowDto] = Field(default_factory=list)
    analytics: ExperimentAnalyticsDto = Field(default_factory=ExperimentAnalyticsDto)
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
            task_counts = _task_counts_by_run(session, [run.id for run in runs])
            run_rows = [_run_row(run, total_tasks=task_counts.get(run.id)) for run in runs]
            return ExperimentDetailDto(
                experiment=_summary(session, experiment, runs=runs),
                runs=run_rows,
                analytics=_analytics(run_rows),
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


def _run_row(run: RunRecord, *, total_tasks: int | None = None) -> ExperimentRunRowDto:
    summary = run.parsed_summary()
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
        worker_team=run.parsed_worker_team(),
        seed=run.seed,
        running_time_ms=_duration_ms(run),
        final_score=_summary_number(summary, "normalized_score")
        or _summary_number(summary, "final_score"),
        total_tasks=total_tasks,
        total_cost_usd=_summary_number(summary, "total_cost_usd"),
        error_message=run.error_message or _summary_text(summary, "error_message"),
    )


def _task_counts_by_run(session, run_ids: list[UUID]) -> dict[UUID, int]:
    return {
        run_id: len(
            list(session.exec(select(RunGraphNode.id).where(RunGraphNode.run_id == run_id)))
        )
        for run_id in run_ids
    }


def _analytics(rows: list[ExperimentRunRowDto]) -> ExperimentAnalyticsDto:
    status_counts = ExperimentStatusCountsDto()
    scores: list[float] = []
    durations: list[int] = []
    task_counts: list[int] = []
    total_cost_usd: float | None = None
    latest_activity_at: datetime | None = None
    error_count = 0

    for row in rows:
        _increment_status_count(status_counts, row.status)
        if row.final_score is not None:
            scores.append(row.final_score)
        if row.running_time_ms is not None:
            durations.append(row.running_time_ms)
        if row.total_tasks is not None:
            task_counts.append(row.total_tasks)
        if row.total_cost_usd is not None:
            total_cost_usd = (total_cost_usd or 0.0) + row.total_cost_usd
        if row.error_message:
            error_count += 1
        activity_at = row.completed_at or row.started_at or row.created_at
        if latest_activity_at is None or activity_at > latest_activity_at:
            latest_activity_at = activity_at

    return ExperimentAnalyticsDto(
        total_runs=len(rows),
        status_counts=status_counts,
        average_score=_average(scores),
        average_duration_ms=round(_average(durations)) if durations else None,
        average_tasks=_average(task_counts),
        total_cost_usd=total_cost_usd,
        latest_activity_at=latest_activity_at,
        error_count=error_count,
    )


def _increment_status_count(counts: ExperimentStatusCountsDto, status: str) -> None:
    match status:
        case "pending":
            counts.pending += 1
        case "executing":
            counts.executing += 1
        case "evaluating":
            counts.evaluating += 1
        case "completed":
            counts.completed += 1
        case "failed":
            counts.failed += 1
        case "cancelled":
            counts.cancelled += 1


def _average(values: list[float] | list[int]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _duration_ms(run: RunRecord) -> int | None:
    if run.started_at is None or run.completed_at is None:
        return None
    return round((run.completed_at - run.started_at).total_seconds() * 1000)


def _summary_number(summary: dict, key: str) -> float | None:
    value = summary.get(key)
    if isinstance(value, int | float):
        return float(value)
    return None


def _summary_text(summary: dict, key: str) -> str | None:
    value = summary.get(key)
    if isinstance(value, str) and value:
        return value
    return None
