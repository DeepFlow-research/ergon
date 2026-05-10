"""Schema tests for task_id-only runtime event contracts."""

from uuid import uuid4

import pytest
from ergon_core.core.application.events.task_events import (
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskReadyEvent,
)
from pydantic import ValidationError


_TASK_EVENTS = [
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
        "TaskCompletedEvent",
        lambda: TaskCompletedEvent(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
            sandbox_id="sbx-123",
        ),
    ),
]


@pytest.mark.parametrize("label,factory", _TASK_EVENTS, ids=[c[0] for c in _TASK_EVENTS])
def test_task_events_require_task_id_and_do_not_dump_node_id(label, factory):
    obj = factory()
    data = obj.model_dump()

    assert obj.task_id is not None
    assert "node_id" not in data


def test_task_ready_event_rejects_missing_task_id() -> None:
    with pytest.raises(ValidationError):
        TaskReadyEvent(run_id=uuid4(), definition_id=uuid4())
