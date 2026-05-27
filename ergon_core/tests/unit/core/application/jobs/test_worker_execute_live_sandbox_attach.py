from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ergon_core.core.jobs.task.execute.contract import TaskReadyEvent
from ergon_core.api.worker.results import WorkerOutput
from ergon_core.core.jobs.task.worker_execute.contract import WorkerExecuteJobRequest
from ergon_core.core.jobs.task.worker_execute.job import run_worker_execute_job


class _FakeWorker:
    def validate_runtime_deps(self) -> None:
        pass

    async def execute(self, task, *, context):
        assert context.sandbox_id == "sbx-live"
        assert task.sandbox.is_live is True
        yield WorkerOutput(output="ok")


class _FakeTaskExecutionService:
    def __init__(self, seen: list[str | None]) -> None:
        self._seen = seen
        self.persisted_outputs = []
        self.attached_sandboxes = []

    async def load_task_view(self, _session, *, sample_id, task_id, sandbox_id=None):
        del sample_id, task_id
        self._seen.append(sandbox_id)
        sandbox = SimpleNamespace(is_live=sandbox_id == "sbx-live")
        return SimpleNamespace(task=SimpleNamespace(worker=_FakeWorker(), sandbox=sandbox))

    async def persist_worker_output(self, _session, *, execution_id, output):
        self.persisted_outputs.append((execution_id, output))

    async def attach_sandbox_to_execution(self, _session, *, execution_id, sandbox_id):
        self.attached_sandboxes.append((execution_id, sandbox_id))


class _FakeSession:
    def commit(self) -> None:
        pass


@pytest.mark.asyncio
async def test_worker_execute_reloads_task_with_live_sandbox_id(monkeypatch) -> None:
    from ergon_core.core.jobs.task.worker_execute import job as module

    seen_sandbox_ids: list[str | None] = []

    async def _persist(*args, **kwargs):
        pass

    async def _publish(_event):
        return None

    task_execution = _FakeTaskExecutionService(seen_sandbox_ids)

    monkeypatch.setattr(module, "get_session", lambda: nullcontext(_FakeSession()))
    monkeypatch.setattr(module, "TaskExecutionService", lambda: task_execution)
    monkeypatch.setattr(module.ContextEventService, "persist_chunk", _persist)
    monkeypatch.setattr(module, "TaskManagementService", lambda **kwargs: object())
    monkeypatch.setattr(module, "TaskInspectionService", lambda: object())
    monkeypatch.setattr(module, "SampleResourceReadService", lambda: object())
    monkeypatch.setattr(
        module,
        "get_dashboard_event_publisher",
        lambda: SimpleNamespace(publish=_publish),
    )

    result = await run_worker_execute_job(
        WorkerExecuteJobRequest(
            sample_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
            sandbox_id="sbx-live",
            task_slug="root",
            task_description="root task",
            assigned_worker_slug="worker",
            worker_type="worker",
            model_target="model",
            benchmark_type="benchmark",
        )
    )

    assert result.success is True
    assert seen_sandbox_ids == ["sbx-live"]


@pytest.mark.asyncio
async def test_worker_execute_rejects_object_bound_worker_without_live_sandbox(
    monkeypatch,
) -> None:
    from ergon_core.core.jobs.task.worker_execute import job as module

    class _NonLiveTaskExecutionService:
        async def load_task_view(self, _session, *, sample_id, task_id, sandbox_id=None):
            del sample_id, task_id, sandbox_id
            return SimpleNamespace(
                task=SimpleNamespace(
                    worker=_FakeWorker(),
                    sandbox=SimpleNamespace(is_live=False),
                )
            )

    monkeypatch.setattr(module, "get_session", lambda: nullcontext(object()))
    monkeypatch.setattr(module, "TaskExecutionService", lambda: _NonLiveTaskExecutionService())
    monkeypatch.setattr(module, "TaskManagementService", lambda: object())
    monkeypatch.setattr(module, "TaskInspectionService", lambda: object())
    monkeypatch.setattr(module, "SampleResourceReadService", lambda: object())

    with pytest.raises(Exception, match="live sandbox"):
        await run_worker_execute_job(
            WorkerExecuteJobRequest(
                sample_id=uuid4(),
                task_id=uuid4(),
                execution_id=uuid4(),
                sandbox_id="sbx-live",
                task_slug="root",
                task_description="root task",
                assigned_worker_slug="worker",
                worker_type="worker",
                model_target="model",
                benchmark_type="benchmark",
            )
        )


@pytest.mark.asyncio
async def test_step_aware_task_management_sends_collected_ready_events(monkeypatch) -> None:
    from ergon_core.core.jobs.task.worker_execute import job as module
    from ergon_core.core.application.runtime import management

    sent: list[tuple[str, object]] = []

    class _Step:
        async def send_event(self, step_id: str, event: object) -> None:
            sent.append((step_id, event))

    task_id = uuid4()
    sample_id = uuid4()

    async def _publish(_event):
        return None

    monkeypatch.setattr(
        management,
        "get_dashboard_event_publisher",
        lambda: SimpleNamespace(publish=_publish),
    )
    service = module._StepAwareTaskManagementService(SimpleNamespace(step=_Step()))
    await service._dispatch_collected_ready_events(
        "plan-subtasks-test",
        [module._ReadyDispatch(sample_id=sample_id, task_id=task_id)],
    )

    assert len(sent) == 1
    step_id, event = sent[0]
    assert step_id == f"plan-subtasks-test-dispatch-task-ready-{task_id}"
    payload = TaskReadyEvent.model_validate(event.data)
    assert event.name == TaskReadyEvent.name
    assert payload.sample_id == sample_id
    assert "definition_id" not in type(payload).model_fields
    assert payload.task_id == task_id
