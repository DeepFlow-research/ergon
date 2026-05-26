"""Public experiment persistence delegator."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ergon_core.api.experiment.experiment import Experiment, ExperimentRef


@runtime_checkable
class ExperimentPersistenceService(Protocol):
    async def persist_experiment(self, experiment: Experiment) -> ExperimentRef: ...


async def persist_experiment(
    experiment: Experiment,
    *,
    service: ExperimentPersistenceService,
) -> ExperimentRef:
    experiment.validate_authoring()
    return await service.persist_experiment(experiment)
