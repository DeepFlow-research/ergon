"""PR 12 schema tests: task_id is required and node_id is not a public bridge."""

from uuid import uuid4

import pytest
from ergon_core.core.application.events.task_events import (
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskReadyEvent,
)
from ergon_core.core.application.workflows.orchestration import (
    PreparedTaskExecution,
    PrepareTaskExecutionCommand,
    PropagateTaskCompletionCommand,
    TaskDescriptor,
)


_TASK_ID_CASES = [
    (
        "TaskReadyEvent",
        lambda: TaskReadyEvent(run_id=uuid4(), definition_id=uuid4(), task_id=uuid4()),
    ),
    (
        "TaskFailedEvent",
        lambda: TaskFailedEvent(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
            error="boom",
        ),
    ),
    (
        "PrepareTaskExecutionCommand",
        lambda: PrepareTaskExecutionCommand(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=uuid4(),
        ),
    ),
    (
        "TaskDescriptor",
        lambda: TaskDescriptor(
            task_id=uuid4(),
            task_slug="test-task",
        ),
    ),
    (
        "PropagateTaskCompletionCommand",
        lambda: PropagateTaskCompletionCommand(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
        ),
    ),
]


def test_task_ready_event_requires_task_id() -> None:
    with pytest.raises(ValueError):
        TaskReadyEvent(run_id=uuid4(), definition_id=uuid4())  # type: ignore[call-arg]


@pytest.mark.parametrize("label,factory", _TASK_ID_CASES, ids=[c[0] for c in _TASK_ID_CASES])
def test_task_id_round_trips(label, factory):
    obj = factory()
    data = obj.model_dump()
    assert "task_id" in data
    assert "node_id" not in data
    roundtripped = type(obj).model_validate(data)
    assert roundtripped.task_id == obj.task_id


def test_task_completed_event_uses_task_id() -> None:
    task_id = uuid4()
    event = TaskCompletedEvent(
        run_id=uuid4(),
        definition_id=uuid4(),
        task_id=task_id,
        execution_id=uuid4(),
        sandbox_id="sbx-123",
    )

    assert event.task_id == task_id
    assert "node_id" not in event.model_dump()
