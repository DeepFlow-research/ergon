"""Module-level launch for previously-persisted benchmark definitions.

Symmetric with the module-level ``persist_benchmark`` in
``definition_writer``: PR 6.5 collapsed both sides of the lifecycle out
of the ``ExperimentService`` façade. Persistence reads identity off the
``Benchmark`` instance; launch reads identity off the
``BenchmarkDefinitionRecord``.
"""

from collections.abc import Awaitable, Callable
from uuid import UUID

from ergon_core.core.application.experiments.launch import (
    _ExperimentRunLauncher,
    launch_run,
)
from ergon_core.core.application.experiments.models import (
    ExperimentRunRequest,
    ExperimentRunResult,
    RunAssignment,
)
from ergon_core.core.domain.experiments import DefinitionHandle
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import BenchmarkDefinitionRecord

WorkflowDefinitionFactory = Callable[
    [BenchmarkDefinitionRecord, RunAssignment],
    DefinitionHandle,
]
WorkflowStartedEmitter = Callable[[UUID, UUID], Awaitable[None]]


async def run_experiment(
    request: ExperimentRunRequest,
    *,
    workflow_definition_factory: WorkflowDefinitionFactory | None = None,
    emit_workflow_started: WorkflowStartedEmitter | None = None,
) -> ExperimentRunResult:
    """Materialize runs for a previously persisted benchmark definition.

    Prefer the new definition-first path: if ``request.experiment_id`` is
    actually an ``ExperimentDefinition`` row, launch directly via
    ``launch_run``. Fall back to the legacy ``BenchmarkDefinitionRecord``
    path only when no definition row matches — i.e. for legacy
    harness-written runs that predate PR 7. PR 11 deletes the fallback
    once all live runs have been re-launched.
    """

    with get_session() as session:
        definition = session.get(ExperimentDefinition, request.experiment_id)
    if definition is not None:
        return await launch_run(
            request.experiment_id,
            emit_workflow_started=emit_workflow_started,
        )

    return await _ExperimentRunLauncher(
        workflow_definition_factory=workflow_definition_factory,
        emit_workflow_started=emit_workflow_started,
    ).run_experiment(request)
