"""Integration tests for dynamically added subtask dispatch."""

from unittest.mock import AsyncMock, patch

import pytest
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.types import (
    AssignedWorkerSlug,
    NodeId,
    RunId,
    TaskSlug,
)
from ergon_core.core.runtime.events.task_events import TaskReadyEvent
from ergon_core.core.runtime.services.task_management_dto import AddSubtaskCommand
from ergon_core.core.runtime.services.task_management_service import TaskManagementService

from tests.integration.propagation._helpers import make_experiment_definition, make_node, make_run
from tests.integration.restart._helpers import cleanup_run

pytestmark = pytest.mark.integration

_TMS_INNGEST = "ergon_core.core.runtime.services.task_management_service.inngest_client"
_EMITTER_INNGEST = "ergon_core.core.dashboard.emitter.inngest_client"


@pytest.mark.asyncio
async def test_add_subtask_dispatches_dependency_free_child() -> None:
    with get_session() as session:
        definition = make_experiment_definition(session)
        run = make_run(session, definition.id)
        parent = make_node(session, run.id, task_slug="root", status="running")
        run_id = run.id
        definition_id = definition.id
        parent_id = parent.id
        session.commit()

    try:
        with patch(_TMS_INNGEST) as task_mgmt_inngest, patch(_EMITTER_INNGEST) as emitter_inngest:
            task_mgmt_inngest.send = AsyncMock()
            emitter_inngest.send = AsyncMock()
            with get_session() as session:
                result = await TaskManagementService().add_subtask(
                    session,
                    AddSubtaskCommand(
                        run_id=RunId(run_id),
                        parent_node_id=NodeId(parent_id),
                        task_slug=TaskSlug("source-scout"),
                        description="Find sources.",
                        assigned_worker_slug=AssignedWorkerSlug("researchrubrics-researcher"),
                    ),
                )

        task_mgmt_inngest.send.assert_awaited_once()
        event = task_mgmt_inngest.send.await_args.args[0]
        assert event.name == TaskReadyEvent.name
        assert event.data["run_id"] == str(run_id)
        assert event.data["definition_id"] == str(definition_id)
        assert event.data["node_id"] == str(result.node_id)
    finally:
        cleanup_run(run_id, definition_id)
