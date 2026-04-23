"""Phase 0 schema tests: node_id on events, DTOs, and optional task_id."""

from uuid import uuid4

import pytest
from ergon_core.api.worker_context import WorkerContext
from ergon_core.core.runtime.events.task_events import (
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskReadyEvent,
)
from ergon_core.core.runtime.services.orchestration_dto import (
    PreparedTaskExecution,
    PrepareTaskExecutionCommand,
    PropagateTaskCompletionCommand,
    TaskDescriptor,
)


class TestDynamicTaskNone:
    def test_task_ready_event_task_id_defaults_to_none(self):
        evt = TaskReadyEvent(run_id=uuid4(), definition_id=uuid4())
        assert evt.task_id is None


_NODE_ID_CASES = [
    (
        "TaskReadyEvent",
        lambda: TaskReadyEvent(run_id=uuid4(), definition_id=uuid4(), task_id=uuid4()),
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
        "PreparedTaskExecution",
        lambda: PreparedTaskExecution(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=uuid4(),
            task_slug="test-task",
            task_description="A test task",
            benchmark_type="test",
            execution_id=uuid4(),
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
    (
        "WorkerContext",
        lambda: WorkerContext(
            run_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
            sandbox_id="sbx-123",
        ),
    ),
]


@pytest.mark.parametrize("label,factory", _NODE_ID_CASES, ids=[c[0] for c in _NODE_ID_CASES])
def test_node_id_defaults_to_none(label, factory):
    obj = factory()
    assert obj.node_id is None
    data = obj.model_dump()
    assert data["node_id"] is None
    roundtripped = type(obj).model_validate(data)
    assert roundtripped.node_id is None


@pytest.mark.parametrize("label,factory", _NODE_ID_CASES, ids=[c[0] for c in _NODE_ID_CASES])
def test_node_id_round_trips(label, factory):
    nid = uuid4()
    obj = factory()
    obj_with_id = type(obj).model_validate({**obj.model_dump(), "node_id": str(nid)})
    assert obj_with_id.node_id == nid
    data = obj_with_id.model_dump()
    roundtripped = type(obj).model_validate(data)
    assert roundtripped.node_id == nid
