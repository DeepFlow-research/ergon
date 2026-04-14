"""Phase 0 schema tests: node_id on events, DTOs, and sentinel constant."""

from uuid import UUID, uuid4

from ergon_core.core.runtime.events.task_events import (
    DYNAMIC_TASK_SENTINEL_ID,
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskReadyEvent,
)
from ergon_core.core.runtime.services.orchestration_dto import (
    PrepareTaskExecutionCommand,
    PreparedTaskExecution,
    PropagateTaskCompletionCommand,
    TaskDescriptor,
)
from ergon_core.api.worker_context import WorkerContext


class TestDynamicTaskSentinel:
    def test_sentinel_is_nil_uuid(self):
        assert DYNAMIC_TASK_SENTINEL_ID == UUID("00000000-0000-0000-0000-000000000000")
        assert int(DYNAMIC_TASK_SENTINEL_ID) == 0


class TestTaskReadyEventNodeId:
    def test_without_node_id(self):
        evt = TaskReadyEvent(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=uuid4(),
        )
        assert evt.node_id is None
        data = evt.model_dump()
        assert data["node_id"] is None
        roundtripped = TaskReadyEvent.model_validate(data)
        assert roundtripped.node_id is None

    def test_with_node_id(self):
        nid = uuid4()
        evt = TaskReadyEvent(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=uuid4(),
            node_id=nid,
        )
        assert evt.node_id == nid
        data = evt.model_dump()
        roundtripped = TaskReadyEvent.model_validate(data)
        assert roundtripped.node_id == nid


class TestTaskCompletedEventNodeId:
    def test_without_node_id(self):
        evt = TaskCompletedEvent(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
            sandbox_id="sbx-123",
        )
        assert evt.node_id is None
        data = evt.model_dump()
        roundtripped = TaskCompletedEvent.model_validate(data)
        assert roundtripped.node_id is None

    def test_with_node_id(self):
        nid = uuid4()
        evt = TaskCompletedEvent(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
            sandbox_id="sbx-123",
            node_id=nid,
        )
        assert evt.node_id == nid
        data = evt.model_dump()
        roundtripped = TaskCompletedEvent.model_validate(data)
        assert roundtripped.node_id == nid


class TestTaskFailedEventNodeId:
    def test_without_node_id(self):
        evt = TaskFailedEvent(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
            error="boom",
        )
        assert evt.node_id is None
        data = evt.model_dump()
        roundtripped = TaskFailedEvent.model_validate(data)
        assert roundtripped.node_id is None

    def test_with_node_id(self):
        nid = uuid4()
        evt = TaskFailedEvent(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
            error="boom",
            node_id=nid,
        )
        assert evt.node_id == nid
        data = evt.model_dump()
        roundtripped = TaskFailedEvent.model_validate(data)
        assert roundtripped.node_id == nid


class TestPrepareTaskExecutionCommandNodeId:
    def test_accepts_node_id(self):
        nid = uuid4()
        cmd = PrepareTaskExecutionCommand(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=uuid4(),
            node_id=nid,
        )
        assert cmd.node_id == nid

    def test_defaults_to_none(self):
        cmd = PrepareTaskExecutionCommand(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=uuid4(),
        )
        assert cmd.node_id is None


class TestPreparedTaskExecutionNodeId:
    def test_accepts_node_id(self):
        nid = uuid4()
        result = PreparedTaskExecution(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=uuid4(),
            task_key="test-task",
            task_description="A test task",
            benchmark_type="test",
            execution_id=uuid4(),
            node_id=nid,
        )
        assert result.node_id == nid

    def test_defaults_to_none(self):
        result = PreparedTaskExecution(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=uuid4(),
            task_key="test-task",
            task_description="A test task",
            benchmark_type="test",
            execution_id=uuid4(),
        )
        assert result.node_id is None


class TestTaskDescriptorNodeId:
    def test_accepts_node_id(self):
        nid = uuid4()
        td = TaskDescriptor(
            task_id=uuid4(),
            task_key="test-task",
            node_id=nid,
        )
        assert td.node_id == nid

    def test_defaults_to_none(self):
        td = TaskDescriptor(
            task_id=uuid4(),
            task_key="test-task",
        )
        assert td.node_id is None


class TestPropagateTaskCompletionCommandNodeId:
    def test_accepts_node_id(self):
        nid = uuid4()
        cmd = PropagateTaskCompletionCommand(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
            node_id=nid,
        )
        assert cmd.node_id == nid

    def test_defaults_to_none(self):
        cmd = PropagateTaskCompletionCommand(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
        )
        assert cmd.node_id is None


class TestWorkerContextNodeId:
    def test_accepts_node_id(self):
        nid = uuid4()
        ctx = WorkerContext(
            run_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
            sandbox_id="sbx-123",
            node_id=nid,
        )
        assert ctx.node_id == nid

    def test_defaults_to_none(self):
        ctx = WorkerContext(
            run_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
            sandbox_id="sbx-123",
        )
        assert ctx.node_id is None
