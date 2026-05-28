"""Application repository helpers for experiment persistence."""

from uuid import UUID

from pydantic import JsonValue
from sqlmodel import Session, select

from ergon_core.api.experiment.experiment import Experiment, PersistedExperiment
from ergon_core.api.experiment.sample import Sample
from ergon_core.core.persistence.experiments.models import (
    ExperimentEnvironmentRow,
    ExperimentRow,
    ExperimentSamplerInvocationRow,
    ExperimentSamplePoolEntryRow,
)
from ergon_core.core.shared.utils import utcnow


class ExperimentRepository:
    """Data-access boundary for experiment authoring persistence."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def persist_experiment(self, experiment: Experiment) -> PersistedExperiment:
        experiment.validate_authoring()
        row = ExperimentRow(
            name=experiment.name,
            description=experiment.description,
            created_by=experiment.created_by,
            metadata_json=experiment.metadata,
        )
        self._session.add(row)
        self._session.flush()

        for environment in experiment.environments:
            self._session.add(
                ExperimentEnvironmentRow(
                    experiment_id=row.id,
                    name=environment.name,
                    source_mode=environment.source_mode,
                    source_metadata_json=environment.source_metadata,
                    metadata_json=environment.metadata,
                )
            )
        self._session.flush()

        environment_ids = {
            environment.name: environment.id
            for environment in self._session.exec(
                select(ExperimentEnvironmentRow).where(
                    ExperimentEnvironmentRow.experiment_id == row.id
                )
            ).all()
        }
        return PersistedExperiment(
            experiment_id=row.id,
            name=row.name,
            environment_ids=environment_ids,
            created_at=row.created_at,
            metadata=row.metadata_json,
        )

    def pending_unselected_pool_entries(
        self,
        experiment_id: UUID,
    ) -> list[ExperimentSamplePoolEntryRow]:
        rows = self._session.exec(
            select(ExperimentSamplePoolEntryRow)
            .where(ExperimentSamplePoolEntryRow.experiment_id == experiment_id)
            .where(ExperimentSamplePoolEntryRow.selected.is_(False))
            .where(ExperimentSamplePoolEntryRow.discarded.is_(False))
            .order_by(ExperimentSamplePoolEntryRow.created_at, ExperimentSamplePoolEntryRow.id)
        ).all()
        return list(rows)

    def experiment_environment_row(
        self,
        *,
        experiment_id: UUID,
        environment_name: str,
    ) -> ExperimentEnvironmentRow:
        return self._session.exec(
            select(ExperimentEnvironmentRow)
            .where(ExperimentEnvironmentRow.experiment_id == experiment_id)
            .where(ExperimentEnvironmentRow.name == environment_name)
        ).one()

    def known_sample_keys_by_environment(self, experiment_id: UUID) -> dict[str, set[str]]:
        rows = self._session.exec(
            select(ExperimentSamplePoolEntryRow, ExperimentEnvironmentRow.name)
            .join(
                ExperimentEnvironmentRow,
                ExperimentSamplePoolEntryRow.environment_id == ExperimentEnvironmentRow.id,
            )
            .where(ExperimentSamplePoolEntryRow.experiment_id == experiment_id)
        ).all()
        known: dict[str, set[str]] = {}
        for entry, environment_name in rows:
            known.setdefault(environment_name, set()).add(entry.sample_key)
        return known

    def record_candidate(
        self,
        *,
        handle: PersistedExperiment,
        environment_id: UUID,
        sample: Sample,
    ) -> ExperimentSamplePoolEntryRow:
        row = ExperimentSamplePoolEntryRow(
            experiment_id=handle.experiment_id,
            environment_id=environment_id,
            sample_key=sample.sample_key,
            sample_ref_json=sample.sample_ref,
            sample_json=sample.model_dump(mode="json"),
        )
        self._session.add(row)
        self._session.flush()
        return row

    def mark_pool_entries_selected(
        self,
        entries: list[ExperimentSamplePoolEntryRow],
        *,
        sampler_invocation_id: UUID,
    ) -> None:
        selected_at = utcnow()
        for entry in entries:
            entry.selected = True
            entry.selected_at = selected_at
            entry.sampler_invocation_id = sampler_invocation_id
            self._session.add(entry)
        self._session.flush()


def persist_experiment(*, session: Session, experiment: Experiment) -> PersistedExperiment:
    return ExperimentRepository(session).persist_experiment(experiment)


def record_sampler_invocation(
    *,
    session: Session,
    experiment_ref: PersistedExperiment,
    sampler_name: str,
    requested_k: int,
    candidate_pool_size: int,
    selected_count: int = 0,
    policy_version: int | None = None,
    sampler_config: dict[str, JsonValue] | None = None,
) -> ExperimentSamplerInvocationRow:
    row = ExperimentSamplerInvocationRow(
        experiment_id=experiment_ref.experiment_id,
        sampler_name=sampler_name,
        requested_k=requested_k,
        candidate_pool_size=candidate_pool_size,
        selected_count=selected_count,
        policy_version=policy_version,
        sampler_config_json=dict(sampler_config or {}),
    )
    session.add(row)
    session.flush()
    return row
