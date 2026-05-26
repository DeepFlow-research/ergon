"""Application repository helpers for experiment persistence."""

from uuid import UUID

from pydantic import JsonValue
from sqlmodel import Session, select

from ergon_core.api.experiment.experiment import Experiment, ExperimentRef
from ergon_core.core.persistence.experiments.models import (
    ExperimentEnvironmentRow,
    ExperimentRow,
    ExperimentSamplerInvocationRow,
)


def persist_experiment(*, session: Session, experiment: Experiment) -> ExperimentRef:
    experiment.validate()
    row = ExperimentRow(
        name=experiment.name,
        description=experiment.description,
        created_by=experiment.created_by,
        metadata_json=experiment.metadata,
    )
    session.add(row)
    session.flush()

    for environment in experiment.environments:
        session.add(
            ExperimentEnvironmentRow(
                experiment_id=row.id,
                name=environment.name,
                source_mode=environment.source_mode,
                source_metadata_json=environment.source_metadata,
                metadata_json=environment.metadata,
            )
        )
    session.flush()

    return ExperimentRef(
        experiment_id=row.id,
        name=row.name,
        environment_ids=_environment_ids_for_experiment(session, row.id),
        created_at=row.created_at,
        metadata=row.metadata_json,
    )


def record_sampler_invocation(
    *,
    session: Session,
    experiment_ref: ExperimentRef,
    sampler_name: str,
    requested_k: int,
    candidate_pool_size: int,
    selected_count: int = 0,
    sampler_config: dict[str, JsonValue] | None = None,
) -> ExperimentSamplerInvocationRow:
    row = ExperimentSamplerInvocationRow(
        experiment_id=experiment_ref.experiment_id,
        sampler_name=sampler_name,
        requested_k=requested_k,
        candidate_pool_size=candidate_pool_size,
        selected_count=selected_count,
        sampler_config_json=dict(sampler_config or {}),
    )
    session.add(row)
    session.flush()
    return row


def _environment_ids_for_experiment(session: Session, experiment_id: UUID) -> dict[str, UUID]:
    rows = session.exec(
        select(ExperimentEnvironmentRow).where(
            ExperimentEnvironmentRow.experiment_id == experiment_id
        )
    ).all()
    return {row.name: row.id for row in rows}
