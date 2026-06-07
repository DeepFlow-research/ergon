from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from ergon_core.core.jobs.task.propagate.contract import TaskFailedEvent
from ergon_core.core.jobs.task.propagate.job import run_propagate_task_failure_job
from ergon_core.core.application.runtime.orchestration import (
    PropagateTaskCompletionCommand,
    PropagationResult,
    WorkflowTerminalState,
)


@pytest.mark.asyncio
async def test_failed_task_propagation_does_not_terminate_sandbox_directly() -> None:
    payload = TaskFailedEvent(
        sample_id=uuid4(),
        definition_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        error="boom",
        sandbox_id="sandbox-real",
    )
    propagation = PropagationResult(
        sample_id=payload.sample_id,
        definition_id=payload.definition_id,
        completed_task_id=payload.task_id,
        ready_tasks=[],
        workflow_terminal_state=WorkflowTerminalState.NONE,
    )

    async def fake_propagate_failure(command: PropagateTaskCompletionCommand):
        assert command.task_id == payload.task_id
        return propagation

    with (
        patch("ergon_core.core.jobs.task.propagate.job.WorkflowService") as workflow_service,
        patch(
            "ergon_core.core.jobs.task.propagate.job.send_job_events",
            new=AsyncMock(),
        ) as send,
    ):
        workflow_service.return_value.propagate_failure = fake_propagate_failure
        await run_propagate_task_failure_job(payload)

    send.assert_awaited_once_with([])
