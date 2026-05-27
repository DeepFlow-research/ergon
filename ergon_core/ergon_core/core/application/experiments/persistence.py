"""Concrete core adapter for the public experiment persistence facade."""

from __future__ import annotations

from sqlmodel import Session

from ergon_core.api.experiment.experiment import Experiment, ExperimentRef
from ergon_core.core.application.experiments.repository import (
    persist_experiment as persist_row_graph,
)


class CoreExperimentPersistencePort:
    """Application-backed implementation of ``api.experiment.persist_experiment``."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def persist_experiment(self, experiment: Experiment) -> ExperimentRef:
        ref = experiment.persisted_ref()
        if ref is not None:
            return ref
        ref = persist_row_graph(session=self._session, experiment=experiment)
        experiment.mark_persisted(ref)
        return ref
