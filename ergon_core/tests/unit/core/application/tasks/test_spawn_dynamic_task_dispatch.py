from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ergon_core.api.task import EmptyTaskPayload, Task
from ergon_core.core.application.runtime.task_management import TaskManagementService
from ergon_core.test_support.task_factory import TestSandbox, TestWorker


class _DynamicTask(Task[EmptyTaskPayload]):
    pass


class _Session:
    def commit(self) -> None:
        pass


@contextmanager
def _session_factory(session):
    yield session


class _FakeGraphRepo:
    def __init__(self) -> None:
        self.added_nodes: list[dict] = []
        self.added_edges: list[dict] = []
        self.parent = SimpleNamespace(task_id=uuid4(), instance_key="sample-1", level=2)

    def add_runtime_event_listener(self, listener) -> None:
        del listener

    def get_node(self, session, *, sample_id, task_id):
        del session, sample_id, task_id
        return self.parent

    async def add_node(self, session, sample_id, **kwargs):
        del session, sample_id
        node = SimpleNamespace(task_id=uuid4(), **kwargs)
        self.added_nodes.append(kwargs)
        return node

    async def add_edge(self, session, sample_id, **kwargs):
        del session, sample_id
        self.added_edges.append(kwargs)


@pytest.mark.asyncio
async def test_spawn_dynamic_task_dispatches_ready_event_when_dependency_free(monkeypatch) -> None:
    from ergon_core.core.application.runtime import management as module

    session = _Session()
    graph_repo = _FakeGraphRepo()
    dispatched: list[dict] = []

    async def dispatch_task_ready(sample_id, task_id):
        dispatched.append({"sample_id": sample_id, "task_id": task_id})

    service = TaskManagementService(
        graph_repo=graph_repo,
        dashboard_emitter=SimpleNamespace(graph_mutation=lambda mutation: None),
        task_ready_dispatcher=dispatch_task_ready,
    )

    monkeypatch.setattr(module, "get_session", lambda: _session_factory(session))
    sample_id = uuid4()

    handle = await service.spawn_dynamic_task(
        sample_id=sample_id,
        parent_task_id=uuid4(),
        task=_DynamicTask(
            task_slug="child",
            instance_key="sample-1",
            description="child task",
            worker=TestWorker(name="worker", model="test:none"),
            sandbox=TestSandbox(),
        ),
    )

    assert dispatched == [
        {
            "sample_id": sample_id,
            "task_id": handle.task_id,
        }
    ]
    node_kwargs = graph_repo.added_nodes[0]
    assert node_kwargs["is_dynamic"] is True
    assert node_kwargs["task_json"]["_type"].endswith(":_DynamicTask")
    assert graph_repo.added_edges == []


@pytest.mark.asyncio
async def test_spawn_dynamic_task_with_dependencies_waits_for_propagation(monkeypatch) -> None:
    from ergon_core.core.application.runtime import management as module

    session = _Session()
    graph_repo = _FakeGraphRepo()
    dispatched: list[dict] = []

    async def dispatch_task_ready(sample_id, task_id):
        dispatched.append({"sample_id": sample_id, "task_id": task_id})

    service = TaskManagementService(
        graph_repo=graph_repo,
        dashboard_emitter=SimpleNamespace(graph_mutation=lambda mutation: None),
        task_ready_dispatcher=dispatch_task_ready,
    )

    monkeypatch.setattr(module, "get_session", lambda: _session_factory(session))
    dependency_id = uuid4()

    await service.spawn_dynamic_task(
        sample_id=uuid4(),
        parent_task_id=uuid4(),
        task=_DynamicTask(
            task_slug="child",
            instance_key="sample-1",
            description="child task",
            worker=TestWorker(name="worker", model="test:none"),
            sandbox=TestSandbox(),
        ),
        depends_on=(dependency_id,),
    )

    assert dispatched == []
    assert graph_repo.added_edges[0]["source_task_id"] == dependency_id
