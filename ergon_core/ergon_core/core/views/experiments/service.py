"""Read service for experiment API views."""

from contextlib import AbstractContextManager
from uuid import UUID

from ergon_core.core.persistence.experiments.models import (
    ExperimentEnvironmentRow,
    ExperimentRow,
    ExperimentSamplerInvocationRow,
)
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import SampleRecord
from ergon_core.core.views.experiments.models import (
    EnvironmentContributionView,
    ExperimentDetailView,
    ExperimentListView,
    ExperimentSampleSummaryView,
    ExperimentSamplesView,
    SamplerInvocationView,
    SamplerInvocationsView,
)
from sqlmodel import Session, col, select


class ExperimentReadService:
    """List/show queries for persisted experiment state."""

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
