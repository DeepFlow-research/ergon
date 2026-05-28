"""Public persistence facade for experiment authoring objects."""

from __future__ import annotations

from typing import Any

from ergon_core.api.experiment.experiment import Experiment, PersistedExperiment


async def persist_experiment(
    experiment: Experiment,
    *,
    session: Any | None = None,
) -> PersistedExperiment:
    from ergon_core.core.application.experiments.persistence import persist_public_experiment

    experiment.validate_authoring()
    return await persist_public_experiment(experiment, session=session)
