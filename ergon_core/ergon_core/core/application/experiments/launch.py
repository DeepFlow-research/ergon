"""Experiment definition launch service."""

from collections.abc import Awaitable, Callable, Mapping
from uuid import UUID

import inngest
from ergon_core.core.application.events.task_events import WorkflowStartedEvent
from ergon_core.core.application.experiments.errors import DefinitionNotFoundError
from ergon_core.core.application.experiments.models import ExperimentRunResult
from ergon_core.core.application.workflows.runs import create_run
from ergon_core.core.application.experiments.handles import DefinitionHandle
from ergon_core.core.infrastructure.inngest.client import inngest_client
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.shared.json_types import JsonValue

WorkflowStartedEmitter = Callable[[UUID, UUID], Awaitable[None]]


async def launch_run(
    definition_id: UUID,
    *,
    assignment_metadata: Mapping[str, JsonValue] | None = None,
    emit_workflow_started: WorkflowStartedEmitter | None = None,
) -> ExperimentRunResult:
    """Materialize a run directly from an ExperimentDefinition row."""

    emitter = emit_workflow_started or _emit_workflow_started
    with get_session() as session:
        definition = session.get(ExperimentDefinition, definition_id)
        if definition is None:
            raise DefinitionNotFoundError(definition_id)
        run = create_run(
            DefinitionHandle(
                definition_id=definition.id,
                benchmark_type=definition.benchmark_type,
            ),
            definition_id=definition.id,
            instance_key="default",
            worker_team_json={},
            evaluator_slug=None,
            model_target=None,
            sandbox_slug=None,
            dependency_extras_json={},
            assignment_json=dict(assignment_metadata or {}),
            seed=None,
        )
    await emitter(run.id, definition_id)
    return ExperimentRunResult(
        definition_id=definition_id,
        run_ids=[run.id],
        definition_ids=[definition_id],
    )


async def _emit_workflow_started(run_id: UUID, definition_id: UUID) -> None:
    event = WorkflowStartedEvent(run_id=run_id, definition_id=definition_id)
    await inngest_client.send(
        inngest.Event(
            name=WorkflowStartedEvent.name,
            data=event.model_dump(mode="json"),
        )
    )
