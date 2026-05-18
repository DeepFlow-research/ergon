"""Module-level launch for persisted object-bound benchmark definitions."""

from collections.abc import Awaitable, Callable
from uuid import UUID

from ergon_core.core.application.experiments.launch import launch_run
from ergon_core.core.application.experiments.models import (
    ExperimentRunRequest,
    ExperimentRunResult,
)

WorkflowStartedEmitter = Callable[[UUID, UUID], Awaitable[None]]


async def run_experiment(
    request: ExperimentRunRequest,
    *,
    emit_workflow_started: WorkflowStartedEmitter | None = None,
) -> ExperimentRunResult:
    """Materialize one run directly from an ExperimentDefinition row."""

    return await launch_run(
        request.experiment_id,
        emit_workflow_started=emit_workflow_started,
    )
