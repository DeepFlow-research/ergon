"""Read service for experiment API views."""

from datetime import datetime
from contextlib import AbstractContextManager
from uuid import UUID

from ergon_core.core.views.experiments.models import (
    EnvironmentContributionView,
    ExperimentAnalyticsDto,
    ExperimentDetailDto,
    ExperimentDetailView,
    ExperimentListView,
    ExperimentRunMetricsDto,
    ExperimentRunRowDto,
    ExperimentSampleSummaryView,
    ExperimentSamplesView,
    ExperimentStatusCountsDto,
    ExperimentSummaryDto,
    ExperimentTagDefinitionDto,
    SamplerInvocationView,
    SamplerInvocationsView,
)
from ergon_core.core.persistence.context.models import SampleContextEvent
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionInstance,
)
from ergon_core.core.persistence.experiments.models import (
    ExperimentEnvironmentRow,
    ExperimentRow,
    ExperimentSamplerInvocationRow,
)
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import SampleRecord
from ergon_core.core.views.samples.metrics import aggregate_run_metrics
from sqlmodel import Session, col, select


class ExperimentReadService:
    """List/show queries for persisted benchmark definitions."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    def list_experiment_states(self, *, limit: int = 50) -> ExperimentListView:
        with self._session_scope() as session:
            rows = list(
                session.exec(
                    select(ExperimentRow)
                    .order_by(col(ExperimentRow.created_at).desc())
                    .limit(limit)
                ).all()
            )
            return ExperimentListView(
                items=[_experiment_state(session, row, include_samples=False) for row in rows]
            )

    def get_experiment_state(self, experiment_id: UUID) -> ExperimentDetailView | None:
        with self._session_scope() as session:
            row = session.get(ExperimentRow, experiment_id)
            if row is None:
                return None
            return _experiment_state(session, row, include_samples=True)

    def list_experiment_samples(self, experiment_id: UUID) -> ExperimentSamplesView | None:
        with self._session_scope() as session:
            if session.get(ExperimentRow, experiment_id) is None:
                return None
            environment_names = _environment_names(session, experiment_id)
            samples = list(
                session.exec(
                    select(SampleRecord)
                    .where(SampleRecord.experiment_id == experiment_id)
                    .order_by(col(SampleRecord.created_at).desc())
                ).all()
            )
            return ExperimentSamplesView(
                items=[
                    _sample_summary_view(sample, environment_names=environment_names)
                    for sample in samples
                ]
            )

    def list_sampler_invocations(self, experiment_id: UUID) -> SamplerInvocationsView | None:
        with self._session_scope() as session:
            if session.get(ExperimentRow, experiment_id) is None:
                return None
            rows = list(
                session.exec(
                    select(ExperimentSamplerInvocationRow)
                    .where(ExperimentSamplerInvocationRow.experiment_id == experiment_id)
                    .order_by(col(ExperimentSamplerInvocationRow.created_at).desc())
                ).all()
            )
            return SamplerInvocationsView(items=[_sampler_invocation_view(row) for row in rows])

    def _session_scope(self) -> AbstractContextManager[Session]:
        if self._session is not None:
            return _ExistingSessionScope(self._session)
        return get_session()

    def list_experiments(self, *, limit: int = 50) -> list[ExperimentSummaryDto]:
        with get_session() as session:
            definitions = list(
                session.exec(
                    select(ExperimentDefinition)
                    .order_by(col(ExperimentDefinition.created_at).desc())
                    .limit(limit)
                ).all()
            )
            summaries: list[tuple[datetime, ExperimentSummaryDto]] = []
            for definition in definitions:
                summaries.append(
                    (
                        definition.created_at,
                        _definition_summary(session, definition),
                    )
                )

            summaries.sort(key=lambda pair: pair[0], reverse=True)
            return [summary for _, summary in summaries[:limit]]

    def get_experiment(self, definition_id: UUID) -> ExperimentDetailDto | None:
        with get_session() as session:
            definition = session.get(ExperimentDefinition, definition_id)
            if definition is not None:
                return _definition_detail(session, definition)

            return None

    def distinct_tags(self) -> list[str]:
        with get_session() as session:
            tags = {
                tag
                for tag in session.exec(select(SampleRecord.experiment)).all()
                if isinstance(tag, str) and tag
            }
        return sorted(tags)

    def definitions_by_tag(self, tag: str) -> list[ExperimentTagDefinitionDto]:
        with get_session() as session:
            runs = list(
                session.exec(
                    select(SampleRecord)
                    .where(SampleRecord.experiment == tag)
                    .order_by(col(SampleRecord.created_at).desc())
                ).all()
            )
            latest_by_definition: dict[UUID, SampleRecord] = {}
            for run in runs:
                if run.definition_id is None:
                    continue
                latest_by_definition.setdefault(run.definition_id, run)

            rows: list[ExperimentTagDefinitionDto] = []
            for definition_id, latest_run in latest_by_definition.items():
                definition = session.get(ExperimentDefinition, definition_id)
                if definition is None:
                    continue
                rows.append(
                    ExperimentTagDefinitionDto(
                        definition_id=definition.id,
                        name=definition.name,
                        benchmark_type=definition.benchmark_type,
                        latest_run_status=str(latest_run.status),
                    )
                )
        return rows


def _definition_summary(
    session: Session,
    definition: ExperimentDefinition,
    *,
    runs: list[SampleRecord] | None = None,
) -> ExperimentSummaryDto:
    """Build a summary DTO from an ``ExperimentDefinition`` row.

    Identity fields (``name``/``description``/``benchmark_type``/``created_by``)
    come directly from the columns Task 1 added.  Run / sample bookkeeping is
    derived: ``SampleRecord.experiment`` indexes grouped runs, and
    ``ExperimentDefinitionInstance`` rows index instances.
    """
    runs = runs if runs is not None else _runs_for_definition_view(session, definition)
    run_count = len(runs)
    sample_count = _instance_count(session, definition.id)
    metadata = definition.parsed_metadata()
    analytics = _analytics([_run_row(run, context_events=[]) for run in runs])
    return ExperimentSummaryDto(
        definition_id=definition.id,
        name=definition.name,
        description=definition.description,
        benchmark_type=definition.benchmark_type,
        sample_count=sample_count,
        status=_experiment_lifecycle_status(
            analytics.status_counts,
            run_count=run_count,
            fallback=str(metadata.get("status", "defined")),
        ),
        default_worker_team=dict_metadata(metadata, "default_worker_team"),
        default_evaluator_slug=optional_str_metadata(metadata, "default_evaluator_slug"),
        default_model_target=optional_str_metadata(metadata, "default_model_target"),
        created_by=definition.created_by,
        created_at=definition.created_at,
        started_at=None,
        completed_at=None,
        run_count=run_count,
        status_counts=analytics.status_counts,
        failure_count=analytics.status_counts.failed,
        latest_activity_at=analytics.latest_activity_at,
        average_score=analytics.average_score,
        average_duration_ms=analytics.average_duration_ms,
        average_tasks=analytics.average_tasks,
        total_cost_usd=analytics.total_cost_usd,
    )


def _definition_detail(
    session: Session,
    definition: ExperimentDefinition,
) -> ExperimentDetailDto:
    """Build a detail DTO from an ``ExperimentDefinition`` row."""
    runs = _runs_for_definition_view(session, definition)
    task_counts = _task_counts_by_sample(session, [run.id for run in runs])
    context_events = _context_events_by_run(session, [run.id for run in runs])
    run_rows = [
        _run_row(
            run,
            total_tasks=task_counts.get(run.id),
            context_events=context_events.get(run.id, []),
        )
        for run in runs
    ]
    return ExperimentDetailDto(
        definition_id=definition.id,
        name=definition.name,
        description=definition.description,
        benchmark_type=definition.benchmark_type,
        experiment=_definition_summary(session, definition, runs=runs),
        runs=run_rows,
        analytics=_analytics(run_rows),
        sample_selection={},
        design={},
        metadata=definition.parsed_metadata(),
    )


def _runs_for_definition_view(
    session: Session,
    definition: ExperimentDefinition,
) -> list[SampleRecord]:
    experiment = optional_str_metadata(definition.parsed_metadata(), "experiment")
    if experiment:
        return list(
            session.exec(select(SampleRecord).where(SampleRecord.experiment == experiment)).all()
        )
    return list(
        session.exec(select(SampleRecord).where(SampleRecord.definition_id == definition.id)).all()
    )


def _instance_count(session: Session, definition_id: UUID) -> int:
    return len(
        list(
            session.exec(
                select(ExperimentDefinitionInstance.id).where(
                    ExperimentDefinitionInstance.experiment_definition_id == definition_id
                )
            )
        )
    )


def _run_row(
    run: SampleRecord,
    *,
    total_tasks: int | None = None,
    context_events: list[SampleContextEvent],
) -> ExperimentRunRowDto:
    summary = run.parsed_summary()
    duration_ms = _duration_ms(run)
    score = _summary_number(summary, "normalized_score") or _summary_number(summary, "final_score")
    error_summary = _error_summary(run, summary)
    aggregated = aggregate_run_metrics(context_events, summary=summary)
    return ExperimentRunRowDto(
        sample_id=run.id,
        definition_id=run.definition_id,
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
        running_time_ms=duration_ms,
        final_score=score,
        total_tasks=total_tasks,
        total_cost_usd=aggregated.total_cost_usd,
        error_message=error_summary,
        metrics=ExperimentRunMetricsDto(
            sample_id=run.id,
            run_name=run.sample_id or run.instance_key,
            status=str(run.status),
            sample_label=run.sample_id,
            instance_key=run.instance_key,
            score=score,
            return_value=score,
            duration_ms=duration_ms,
            total_tasks=total_tasks,
            tool_call_count=aggregated.tool_call_count,
            total_tokens=aggregated.total_tokens,
            token_breakdown=aggregated.token_breakdown,
            total_cost_usd=aggregated.total_cost_usd,
            cost_observed=aggregated.cost_observed,
            model_target=run.model_target,
            evaluator_slug=run.evaluator_slug,
            error_summary=error_summary,
        ),
    )


def _task_counts_by_sample(session: Session, sample_ids: list[UUID]) -> dict[UUID, int]:
    return {
        sample_id: len(
            list(
                session.exec(
                    select(SampleGraphNode.task_id).where(SampleGraphNode.sample_id == sample_id)
                )
            )
        )
        for sample_id in sample_ids
    }


def _context_events_by_run(
    session: Session,
    sample_ids: list[UUID],
) -> dict[UUID, list[SampleContextEvent]]:
    if not sample_ids:
        return {}

    rows = list(
        session.exec(
            select(SampleContextEvent).where(col(SampleContextEvent.sample_id).in_(sample_ids))
        )
    )
    result: dict[UUID, list[SampleContextEvent]] = {sample_id: [] for sample_id in sample_ids}
    for row in rows:
        result.setdefault(row.sample_id, []).append(row)
    return result


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
        if row.metrics.cost_observed and row.total_cost_usd is not None:
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
        average_duration_ms=_rounded_average(durations),
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


def _experiment_lifecycle_status(
    counts: ExperimentStatusCountsDto,
    *,
    run_count: int,
    fallback: str,
) -> str:
    if counts.executing > 0:
        return "executing"
    if counts.evaluating > 0:
        return "evaluating"
    if counts.pending > 0:
        return "pending"
    if run_count == 0:
        return fallback
    if counts.failed > 0:
        return "failed"
    if counts.cancelled > 0 and counts.completed == 0:
        return "cancelled"
    if counts.completed == run_count:
        return "completed"
    if counts.cancelled > 0:
        return "cancelled"
    return fallback


class _ExistingSessionScope:
    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *args: object) -> None:
        return None


def _experiment_state(
    session: Session,
    row: ExperimentRow,
    *,
    include_samples: bool,
) -> ExperimentDetailView:
    environments = list(
        session.exec(
            select(ExperimentEnvironmentRow).where(ExperimentEnvironmentRow.experiment_id == row.id)
        ).all()
    )
    environment_names = {environment.id: environment.name for environment in environments}
    sample_rows = list(
        session.exec(select(SampleRecord).where(SampleRecord.experiment_id == row.id)).all()
    )
    selected_by_environment: dict[UUID, int] = {}
    for sample in sample_rows:
        if sample.environment_id is not None:
            selected_by_environment[sample.environment_id] = (
                selected_by_environment.get(sample.environment_id, 0) + 1
            )
    sampler_rows = list(
        session.exec(
            select(ExperimentSamplerInvocationRow).where(
                ExperimentSamplerInvocationRow.experiment_id == row.id
            )
        ).all()
    )
    return ExperimentDetailView(
        experiment_id=row.id,
        name=row.name,
        description=row.description,
        environments=[
            EnvironmentContributionView(
                environment_id=environment.id,
                environment_name=environment.name,
                source_mode=environment.source_mode,
                sample_count=selected_by_environment.get(environment.id, 0),
                selected_count=selected_by_environment.get(environment.id, 0),
                source_metadata=environment.source_metadata_json,
            )
            for environment in environments
        ],
        sample_count=len(sample_rows),
        samples=[
            _sample_summary_view(sample, environment_names=environment_names)
            for sample in sample_rows
            if include_samples
        ],
        sampler_invocations=[_sampler_invocation_view(invocation) for invocation in sampler_rows],
        metadata=row.metadata_json,
        created_at=row.created_at,
    )


def _environment_names(session: Session, experiment_id: UUID) -> dict[UUID, str]:
    rows = session.exec(
        select(ExperimentEnvironmentRow).where(
            ExperimentEnvironmentRow.experiment_id == experiment_id
        )
    ).all()
    return {row.id: row.name for row in rows}


def _sample_summary_view(
    sample: SampleRecord,
    *,
    environment_names: dict[UUID, str],
) -> ExperimentSampleSummaryView:
    if sample.experiment_id is None or sample.environment_id is None:
        raise ValueError("Sample is missing experiment/environment provenance")
    environment_name = environment_names.get(sample.environment_id)
    if environment_name is None:
        raise ValueError(
            f"Sample {sample.id} points at missing environment {sample.environment_id}"
        )
    assignment = sample.parsed_assignment()
    source_metadata = assignment.get("source_metadata", {})
    return ExperimentSampleSummaryView(
        sample_id=sample.id,
        experiment_id=sample.experiment_id,
        environment_id=sample.environment_id,
        environment_name=environment_name,
        sample_key=sample.sample_key or sample.instance_key,
        sample_ref=sample.sample_ref_json,
        source_metadata=source_metadata if isinstance(source_metadata, dict) else {},
        status=str(sample.status),
        created_at=sample.created_at,
    )


def _sampler_invocation_view(row: ExperimentSamplerInvocationRow) -> SamplerInvocationView:
    return SamplerInvocationView(
        sampler_invocation_id=row.id,
        sampler_name=row.sampler_name,
        requested_k=row.requested_k,
        candidate_pool_size=row.candidate_pool_size,
        selected_count=row.selected_count,
        sampler_config=row.sampler_config_json,
        created_at=row.created_at,
    )


def _average(values: list[float] | list[int]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _rounded_average(values: list[int]) -> int | None:
    average = _average(values)
    return None if average is None else round(average)


def _duration_ms(run: SampleRecord) -> int | None:
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


def _error_summary(run: SampleRecord, summary: dict) -> str | None:
    if run.error_message:
        return run.error_message
    if str(run.status) not in {"failed", "cancelled"}:
        return None
    return _summary_text(summary, "error_message")


def dict_metadata(metadata: dict, key: str) -> dict:
    value = metadata.get(key)
    return dict(value) if isinstance(value, dict) else {}


def optional_str_metadata(metadata: dict, key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) else None
