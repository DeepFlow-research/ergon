from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ergon_core.api.worker.results import WorkerOutput
from ergon_core.core.application.jobs.models import WorkerExecuteJobRequest
from ergon_core.core.application.jobs.worker_execute import run_worker_execute_job


class _FakeWorker:
    def validate_runtime_deps(self) -> None:
        pass

    async def execute(self, task, *, context):
        assert context.sandbox_id == "sbx-live"
        assert task.sandbox.is_live is True
        yield WorkerOutput(output="ok")


class _FakeGraphRepo:
    def __init__(self, seen: list[str | None]) -> None:
        self._seen = seen

    async def node(self, _session, *, run_id, task_id, sandbox_id=None):
        del run_id, task_id
        self._seen.append(sandbox_id)
        sandbox = SimpleNamespace(is_live=sandbox_id == "sbx-live")
        return SimpleNamespace(task=SimpleNamespace(worker=_FakeWorker(), sandbox=sandbox))


class _FakeSession:
    def commit(self) -> None:
        pass


@pytest.mark.asyncio
async def test_worker_execute_reloads_task_with_live_sandbox_id(monkeypatch) -> None:
    from ergon_core.core.application.jobs import worker_execute as module

    seen_sandbox_ids: list[str | None] = []

    async def _persist(*args, **kwargs):
        pass

    monkeypatch.setattr(module, "get_session", lambda: nullcontext(_FakeSession()))
    monkeypatch.setattr(module, "WorkflowGraphRepository", lambda: _FakeGraphRepo(seen_sandbox_ids))
    monkeypatch.setattr(module.WorkerOutputRepository, "persist", _persist)
    monkeypatch.setattr(module.TaskExecutionRepository, "set_sandbox_id", _persist)
    monkeypatch.setattr(module.ContextEventService, "persist_chunk", _persist)
    monkeypatch.setattr(module, "TaskManagementService", lambda: object())
    monkeypatch.setattr(module, "TaskInspectionService", lambda: object())
    monkeypatch.setattr(module, "RunResourceRepository", lambda: object())
    monkeypatch.setattr(module, "get_dashboard_emitter", lambda: SimpleNamespace(
        on_context_event=lambda event: None,
        register_execution=lambda **kwargs: None,
    ))

    result = await run_worker_execute_job(
        WorkerExecuteJobRequest(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=uuid4(),
            node_id=uuid4(),
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
    from ergon_core.core.application.jobs import worker_execute as module

    class _NonLiveRepo:
        async def node(self, _session, *, run_id, task_id, sandbox_id=None):
            del run_id, task_id, sandbox_id
            return SimpleNamespace(
                task=SimpleNamespace(
                    worker=_FakeWorker(),
                    sandbox=SimpleNamespace(is_live=False),
                )
            )

    monkeypatch.setattr(module, "get_session", lambda: nullcontext(object()))
    monkeypatch.setattr(module, "WorkflowGraphRepository", lambda: _NonLiveRepo())
    monkeypatch.setattr(module, "TaskManagementService", lambda: object())
    monkeypatch.setattr(module, "TaskInspectionService", lambda: object())
    monkeypatch.setattr(module, "RunResourceRepository", lambda: object())

    with pytest.raises(Exception, match="live sandbox"):
        await run_worker_execute_job(
            WorkerExecuteJobRequest(
                run_id=uuid4(),
                definition_id=uuid4(),
                task_id=uuid4(),
                node_id=uuid4(),
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
