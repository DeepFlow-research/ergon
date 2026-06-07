"""Module-level launch for persisted object-bound benchmark definitions."""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING
from uuid import UUID

from ergon_core.core.application.experiments.models import (
    DefinitionHandle,
    ExperimentRunRequest,
    ExperimentRunResult,
)

if TYPE_CHECKING:
    from ergon_core.api.benchmark import Benchmark

WorkflowStartedEmitter = Callable[[UUID, UUID], Awaitable[None]]


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
