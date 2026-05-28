"""Concrete core persistence service for public experiment authoring objects."""

from __future__ import annotations

from sqlmodel import Session

from ergon_core.api.experiment.experiment import Experiment, PersistedExperiment
from ergon_core.core.application.experiments.repository import (
    persist_experiment as persist_row_graph,
)
from ergon_core.core.persistence.shared.db import get_session


class ExperimentPersistenceService:
    """Application-backed persistence for public ``Experiment`` objects."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def persist_experiment(self, experiment: Experiment) -> PersistedExperiment:
        persisted = experiment.persisted_experiment()
        if persisted is not None:
            return persisted
        persisted = persist_row_graph(session=self._session, experiment=experiment)
        experiment.mark_persisted(persisted)
        return persisted


async def persist_public_experiment(
    experiment: Experiment,
    *,
    session: Session | None = None,
) -> PersistedExperiment:
    if session is not None:
        return await ExperimentPersistenceService(session).persist_experiment(experiment)
    with get_session() as managed_session:
        persisted = await ExperimentPersistenceService(managed_session).persist_experiment(
            experiment
        )
        managed_session.commit()
        return persisted
