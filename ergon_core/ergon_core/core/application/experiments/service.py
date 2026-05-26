"""Module-level launch for persisted object-bound benchmark definitions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import UUID

from ergon_core.core.application.experiments.models import (
    DefinitionHandle,
    ExperimentRunRequest,
    ExperimentRunResult,
)

if TYPE_CHECKING:
    from ergon_core.api.benchmark import Benchmark
    from ergon_core.api.experiment.experiment import (
        Experiment,
        ExperimentRef,
        ExperimentSubmitResult,
    )
    from ergon_core.api.experiment.sampling import Sampler

WorkflowStartedEmitter = Callable[[UUID, UUID], Awaitable[None]]


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
class PersistExperimentPort(Protocol):
    # TODO(PR04): replace this protocol with the concrete core persistence
    # service once experiment/environment/candidate-pool rows exist.
    async def persist_experiment(self, experiment: "Experiment") -> "ExperimentRef": ...


async def persist_experiment(
    experiment: "Experiment",
    *,
    service: PersistExperimentPort,
) -> "ExperimentRef":
    # TODO(PR04): move callers to the concrete core persistence entry point
    # after experiment rows and environment rows are introduced.
    experiment.validate_authoring()
    return await service.persist_experiment(experiment)


def persist_benchmark(benchmark: "Benchmark") -> DefinitionHandle:
    """Persist a configured object-bound Benchmark as an experiment definition."""

    from ergon_core.core.application.experiments.definition_writer import (
        persist_benchmark as _persist_benchmark,
    )

    return _persist_benchmark(benchmark)


async def launch_sample(
    definition_id: UUID,
    *,
    emit_workflow_started: WorkflowStartedEmitter | None = None,
) -> ExperimentRunResult:
    """Launch a persisted definition while keeping the heavy runtime import lazy."""

    # reason: keep HTTP app imports from cycling through runtime models and public API exports.
    from ergon_core.core.application.experiments.launch import launch_sample as _launch_sample

    return await _launch_sample(
        definition_id,
        emit_workflow_started=emit_workflow_started,
    )


async def run_experiment(
    request: ExperimentRunRequest,
    *,
    emit_workflow_started: WorkflowStartedEmitter | None = None,
) -> ExperimentRunResult:
    """Materialize one sample directly from an ExperimentDefinition row."""

    return await launch_sample(
        request.definition_id,
        emit_workflow_started=emit_workflow_started,
    )


launch_run = launch_sample
