from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from ergon_core.core.application.events.task_events import TaskFailedEvent
from ergon_core.core.application.jobs.propagate_execution import run_propagate_task_failure_job
from ergon_core.core.application.workflows.orchestration import (
    PropagateTaskCompletionCommand,
    PropagationResult,
    WorkflowTerminalState,
)


@pytest.mark.asyncio
async def test_failed_task_propagation_does_not_terminate_sandbox_directly() -> None:
    payload = TaskFailedEvent(
        run_id=uuid4(),
        definition_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        error="boom",
        sandbox_id="sandbox-real",
    )
    propagation = PropagationResult(
        run_id=payload.run_id,
        definition_id=payload.definition_id,
        completed_task_id=payload.task_id,
        ready_tasks=[],
        workflow_terminal_state=WorkflowTerminalState.NONE,
    )

    async def fake_propagate_failure(command: PropagateTaskCompletionCommand):
        assert command.task_id == payload.task_id
        return propagation

    with (
        patch(
            "ergon_core.core.application.jobs.propagate_execution.WorkflowService"
        ) as workflow_service,
        patch(
            "ergon_core.core.application.jobs.propagate_execution.inngest_client.send",
            new=AsyncMock(),
        ) as send,
    ):
        workflow_service.return_value.propagate_failure = fake_propagate_failure
        await run_propagate_task_failure_job(payload)

    send.assert_not_awaited()
