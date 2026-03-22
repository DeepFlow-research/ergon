from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from h_arcane.core._internal.task.events import TaskFailedEvent
from h_arcane.core._internal.task.inngest_functions.task_propagate import (
    task_failure_propagate,
)
from h_arcane.core._internal.task.services import TaskPropagationService
from h_arcane.core._internal.task.services.dto import (
    PropagateTaskCompletionCommand,
    PropagationResult,
    WorkflowTerminalState,
)


class FakeStepRunner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(self, name: str, fn, output_type=None):  # noqa: ANN001
        del output_type
        self.calls.append(name)
        result = fn()
        if inspect.isawaitable(result):
            return await result
        return result


class FakeContext:
    def __init__(self, event_data: dict[str, object]) -> None:
        self.event = SimpleNamespace(data=event_data)
        self.step = FakeStepRunner()


def test_task_failure_propagate_is_registered_for_task_failed_events() -> None:
    assert len(task_failure_propagate._triggers) == 1
    trigger = cast(Any, task_failure_propagate._triggers[0])
    assert trigger.event == TaskFailedEvent.name


@patch("h_arcane.core._internal.task.services.task_propagation_service.is_workflow_failed")
def test_propagate_failure_marks_run_terminal(mock_is_workflow_failed) -> None:
    run_id = uuid4()
    experiment_id = uuid4()
    task_id = uuid4()
    execution_id = uuid4()
    mock_is_workflow_failed.return_value = True

    result = TaskPropagationService().propagate_failure(
        PropagateTaskCompletionCommand(
            run_id=run_id,
            experiment_id=experiment_id,
            task_id=task_id,
            execution_id=execution_id,
        )
    )

    assert result == PropagationResult(
        run_id=run_id,
        experiment_id=experiment_id,
        completed_task_id=task_id,
        ready_tasks=[],
        workflow_terminal_state=WorkflowTerminalState.FAILED,
    )


@pytest.mark.asyncio
async def test_task_failure_handler_emits_workflow_failed_for_single_failed_leaf() -> None:
    run_id = uuid4()
    experiment_id = uuid4()
    task_id = uuid4()
    execution_id = uuid4()
    ctx = FakeContext(
        TaskFailedEvent(
            run_id=run_id,
            experiment_id=experiment_id,
            task_id=task_id,
            execution_id=execution_id,
            error="Max turns exceeded",
        ).model_dump(mode="json")
    )
    propagation_result = PropagationResult(
        run_id=run_id,
        experiment_id=experiment_id,
        completed_task_id=task_id,
        ready_tasks=[],
        workflow_terminal_state=WorkflowTerminalState.FAILED,
    )

    with (
        patch(
            "h_arcane.core._internal.task.inngest_functions.task_propagate._propagate_failure",
            new=AsyncMock(return_value=propagation_result),
        ) as mock_propagate_failure,
        patch(
            "h_arcane.core._internal.task.inngest_functions.task_propagate._emit_workflow_failed",
            new=AsyncMock(return_value=None),
        ) as mock_emit_workflow_failed,
    ):
        handler = cast(Any, task_failure_propagate._handler)
        result = await handler(ctx)

    assert result.run_id == run_id
    assert result.task_id == task_id
    assert result.newly_ready_tasks == 0
    assert result.workflow_complete is False
    assert result.workflow_failed is True
    assert ctx.step.calls == ["propagate-failure", "emit-workflow-failed"]
    mock_propagate_failure.assert_awaited_once_with(
        run_id,
        experiment_id,
        task_id,
        execution_id,
    )
    mock_emit_workflow_failed.assert_awaited_once_with(run_id, experiment_id)
