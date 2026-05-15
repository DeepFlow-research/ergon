"""Single front-door service for experiment persistence and launch."""

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from ergon_core.api.benchmark import Benchmark
from ergon_core.core.domain.experiments import DefinitionHandle
from ergon_core.core.persistence.telemetry.models import BenchmarkDefinitionRecord
from ergon_core.core.application.experiments.models import (
    ExperimentRunRequest,
    ExperimentRunResult,
    RunAssignment,
)

WorkflowDefinitionFactory = Callable[
    [BenchmarkDefinitionRecord, RunAssignment],
    DefinitionHandle,
]
WorkflowStartedEmitter = Callable[[UUID, UUID], Awaitable[None]]


class ExperimentService:
    """Persist benchmark definitions and launch runs."""

    def __init__(
        self,
        *,
        workflow_definition_factory: WorkflowDefinitionFactory | None = None,
        emit_workflow_started: WorkflowStartedEmitter | None = None,
    ) -> None:
        self._workflow_definition_factory = workflow_definition_factory
        self._emit_workflow_started = emit_workflow_started

    def persist_benchmark(
        self,
        benchmark: Benchmark,
        *,
        name: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
        created_by: str | None = None,
    ) -> DefinitionHandle:
        """Persist a configured Benchmark as immutable workflow definition rows."""
        from ergon_core.core.application.experiments.definition_writer import (  # slopcop: ignore[guarded-function-import] -- reason: keep heavy definition writer private to the lifecycle service
            persist_benchmark as _persist_benchmark,
        )

        return _persist_benchmark(
            benchmark,
            name=name,
            description=description,
            metadata=metadata,
            created_by=created_by,
        )

    async def run_experiment(self, request: ExperimentRunRequest) -> ExperimentRunResult:
        """Materialize runs for a previously defined experiment."""
        from ergon_core.core.application.experiments.launch import (  # slopcop: ignore[guarded-function-import] -- reason: launch helper is private runtime plumbing behind this front door
            _ExperimentRunLauncher,
        )

        return await _ExperimentRunLauncher(
            workflow_definition_factory=self._workflow_definition_factory,
            emit_workflow_started=self._emit_workflow_started,
        ).run_experiment(request)
