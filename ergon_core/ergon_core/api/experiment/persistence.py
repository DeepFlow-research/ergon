"""Public persistence facade for experiment authoring objects."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ergon_core.api.experiment.experiment import Experiment, ExperimentRef


# PR03 only defines the public seam. PR04 must provide the concrete
# application-backed adapter, and PR05 submit paths must call that adapter rather
# than passing bespoke fake ports around. Keep this protocol thin so public API
# code never imports SQLModel repositories directly.
@runtime_checkable
class PersistExperimentPort(Protocol):
    async def persist_experiment(self, experiment: Experiment) -> ExperimentRef: ...


async def persist_experiment(
    experiment: Experiment,
    *,
    service: PersistExperimentPort,
) -> ExperimentRef:
    experiment.validate_authoring()
    return await service.persist_experiment(experiment)
