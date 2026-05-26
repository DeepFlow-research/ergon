"""Temporary service contracts for the public experiment authoring surface."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from ergon_core.api.experiment.sampling import Sampler


if TYPE_CHECKING:
    from ergon_core.api.experiment.experiment import (
        Experiment,
        ExperimentRef,
        ExperimentSubmitResult,
    )


@runtime_checkable
class ExperimentSubmissionService(Protocol):
    # TODO(PR05): replace this protocol with the concrete core submission service
    # once sample materialization is wired into the runtime path.
    async def submit(
        self,
        *,
        experiment: "Experiment",
        k: int,
        sampler: Sampler,
        candidate_pool_size: int | None,
        policy_version: int | None,
    ) -> "ExperimentSubmitResult": ...


@runtime_checkable
class ExperimentPersistenceService(Protocol):
    # TODO(PR04): replace this protocol with the concrete core persistence
    # service once experiment/environment/candidate-pool rows exist.
    async def persist_experiment(self, experiment: "Experiment") -> "ExperimentRef": ...


async def persist_experiment(
    experiment: "Experiment",
    *,
    service: ExperimentPersistenceService,
) -> "ExperimentRef":
    # TODO(PR04): move callers to the concrete core persistence entry point
    # after experiment rows and environment rows are introduced.
    experiment.validate_authoring()
    return await service.persist_experiment(experiment)
