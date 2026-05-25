from uuid import uuid4

import pytest

from ergon_core.api.worker.results import WorkerOutput
from ergon_core.core.application.runtime.task_execution import TaskExecutionService


class _GraphRepo:
    def __init__(self) -> None:
        self.calls = []

    async def node(self, session, *, sample_id, task_id, sandbox_id=None):
        self.calls.append(
            {
                "session": session,
                "sample_id": sample_id,
                "task_id": task_id,
                "sandbox_id": sandbox_id,
            }
        )
        return object()


class _TaskExecutionRepo:
    def __init__(self) -> None:
        self.sandbox_calls = []

    async def set_sandbox_id(self, session, *, execution_id, sandbox_id):
        self.sandbox_calls.append(
            {
                "session": session,
                "execution_id": execution_id,
                "sandbox_id": sandbox_id,
            }
        )


class _WorkerOutputRepo:
    def __init__(self) -> None:
        self.persist_calls = []
        self.loaded = WorkerOutput(success=True, output="ok")

    async def persist(self, session, *, execution_id, output):
        self.persist_calls.append(
            {
                "session": session,
                "execution_id": execution_id,
                "output": output,
            }
        )

    async def load(self, session, *, execution_id):
        return self.loaded


@pytest.mark.asyncio
async def test_task_execution_facade_loads_task_view_by_task_id() -> None:
    graph_repo = _GraphRepo()
    service = TaskExecutionService(graph_repo=graph_repo)
    session = object()
    sample_id = uuid4()
    task_id = uuid4()

    view = await service.load_task_view(
        session,
        sample_id=sample_id,
        task_id=task_id,
        sandbox_id="sandbox-1",
    )

    assert view is not None
    assert graph_repo.calls == [
        {
            "session": session,
            "sample_id": sample_id,
            "task_id": task_id,
            "sandbox_id": "sandbox-1",
        }
    ]


@pytest.mark.asyncio
async def test_task_execution_facade_owns_worker_output_and_sandbox_writes() -> None:
    task_execution_repo = _TaskExecutionRepo()
    worker_output_repo = _WorkerOutputRepo()
    service = TaskExecutionService(
        task_execution_repo=task_execution_repo,
        worker_output_repo=worker_output_repo,
    )
    session = object()
    execution_id = uuid4()
    output = WorkerOutput(success=True, output="hello")

    await service.persist_worker_output(session, execution_id=execution_id, output=output)
    await service.attach_sandbox_to_execution(
        session,
        execution_id=execution_id,
        sandbox_id="sandbox-2",
    )
    loaded = await service.load_worker_output(session, execution_id=execution_id)

    assert worker_output_repo.persist_calls == [
        {
            "session": session,
            "execution_id": execution_id,
            "output": output,
        }
    ]
    assert task_execution_repo.sandbox_calls == [
        {
            "session": session,
            "execution_id": execution_id,
            "sandbox_id": "sandbox-2",
        }
    ]
    assert loaded is worker_output_repo.loaded
