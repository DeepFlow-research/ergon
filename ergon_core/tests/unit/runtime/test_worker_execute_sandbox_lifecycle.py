from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import ClassVar
from uuid import uuid4

import pytest

from ergon_core.api import Sandbox, Task, Worker, WorkerContext, WorkerOutput
from ergon_core.api.worker import WorkerStreamItem
from ergon_core.core.application.jobs.models import WorkerExecuteJobRequest
import ergon_core.core.application.jobs.worker_execute as worker_execute_module


class _Sandbox(Sandbox):
    provisioned: bool = False
    terminated: bool = False

    async def provision(self) -> None:
        self.provisioned = True

    async def terminate(self) -> None:
        self.terminated = True


class _Worker(Worker):
    type_slug: ClassVar[str] = "lifecycle-worker"
    saw_live_sandbox: bool = False

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
        sandbox: Sandbox,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        self.saw_live_sandbox = isinstance(sandbox, _Sandbox) and sandbox.provisioned
        yield WorkerOutput(output=str(task.task_id), success=self.saw_live_sandbox)


@pytest.mark.asyncio
async def test_worker_execute_acquires_and_keeps_task_sandbox_live(monkeypatch) -> None:
    run_id = uuid4()
    task_id = uuid4()
    worker = _Worker(name="worker", model=None)
    sandbox = _Sandbox()
    task = Task(
        task_slug="root",
        instance_key="default",
        description="Run root",
        worker=worker,
        sandbox=sandbox,
    )
    object.__setattr__(task, "_task_id", task_id)

    class _Repo:
        def node(self, session, *, run_id, task_id):
            return SimpleNamespace(task_id=task_id, task_json=task.to_definition())

    monkeypatch.setattr(worker_execute_module, "WorkflowGraphRepository", _Repo)
    monkeypatch.setattr(worker_execute_module, "TaskManagementService", lambda: object())
    monkeypatch.setattr(worker_execute_module, "TaskInspectionService", lambda: object())
    monkeypatch.setattr(worker_execute_module, "RunResourceRepository", lambda: object())
    monkeypatch.setattr(worker_execute_module, "get_session", lambda: _SessionContext())
    monkeypatch.setattr(worker_execute_module, "ContextEventService", _ContextEventService)
    monkeypatch.setattr(
        worker_execute_module,
        "get_dashboard_emitter",
        lambda: _DashboardEmitter(),
    )
    monkeypatch.setattr(worker_execute_module, "get_trace_sink", lambda: _TraceSink())

    result = await worker_execute_module.run_worker_execute_job(
        WorkerExecuteJobRequest(
            run_id=run_id,
            definition_id=uuid4(),
            task_id=task_id,
            execution_id=uuid4(),
            sandbox_id="legacy-event-id",
        )
    )

    assert result.success is True
    assert result.final_assistant_message == str(task_id)


class _SessionContext:
    def __enter__(self):
        return object()

    def __exit__(self, *args) -> None:
        return None


class _ContextEventService:
    def add_listener(self, listener) -> None:
        return None


class _DashboardEmitter:
    def on_context_event(self, event) -> None:
        return None

    def register_execution(self, *, execution_id, task_node_id) -> None:
        return None


class _TraceSink:
    def emit_span(self, span) -> None:
        return None
