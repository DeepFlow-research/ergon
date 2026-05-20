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


async def run_experiment(
    request: ExperimentRunRequest,
    *,
    emit_workflow_started: WorkflowStartedEmitter | None = None,
) -> ExperimentRunResult:
    """Materialize one run directly from an ExperimentDefinition row."""

    # reason: keep HTTP app imports from cycling through runtime models and public API exports.
    from ergon_core.core.application.experiments.launch import launch_run

    return await launch_run(
        request.definition_id,
        emit_workflow_started=emit_workflow_started,
    )
