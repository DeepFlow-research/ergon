from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ergon_core.api.benchmark.task import EmptyTaskPayload, Task
from ergon_core.core.application.tasks.management import TaskManagementService
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
        self.parent = SimpleNamespace(id=uuid4(), instance_key="sample-1", level=2)

    def add_mutation_listener(self, listener) -> None:
        del listener

    def get_node(self, session, *, run_id, node_id):
        del session, run_id, node_id
        return self.parent

    async def add_node(self, session, run_id, **kwargs):
        del session, run_id
        node = SimpleNamespace(id=uuid4(), **kwargs)
        self.added_nodes.append(kwargs)
        return node

    async def add_edge(self, session, run_id, **kwargs):
        del session, run_id
        self.added_edges.append(kwargs)


@pytest.mark.asyncio
async def test_spawn_dynamic_task_dispatches_ready_event_when_dependency_free(monkeypatch) -> None:
    from ergon_core.core.application.tasks import management as module

    session = _Session()
    graph_repo = _FakeGraphRepo()
    service = TaskManagementService(
        graph_repo=graph_repo,
        dashboard_emitter=SimpleNamespace(graph_mutation=lambda mutation: None),
    )
    dispatched: list[dict] = []

    monkeypatch.setattr(module, "get_session", lambda: _session_factory(session))
    service._resolve_definition_id = lambda _session, _run_id: uuid4()

    async def _dispatch_task_ready(**kwargs):
        dispatched.append(kwargs)

    service._dispatch_task_ready = _dispatch_task_ready

    handle = await service.spawn_dynamic_task(
        run_id=uuid4(),
        parent_task_id=uuid4(),
        task=_DynamicTask(
            task_slug="child",
            instance_key="sample-1",
            description="child task",
            worker=TestWorker(name="worker", model=None),
            sandbox=TestSandbox(),
        ),
    )

    assert dispatched == [
        {
            "run_id": dispatched[0]["run_id"],
            "definition_id": dispatched[0]["definition_id"],
            "node_id": handle.task_id,
        }
    ]
    node_kwargs = graph_repo.added_nodes[0]
    assert node_kwargs["is_dynamic"] is True
    assert node_kwargs["task_json"]["_type"].endswith(":_DynamicTask")
    assert graph_repo.added_edges == []


@pytest.mark.asyncio
async def test_spawn_dynamic_task_with_dependencies_waits_for_propagation(monkeypatch) -> None:
    from ergon_core.core.application.tasks import management as module

    session = _Session()
    graph_repo = _FakeGraphRepo()
    service = TaskManagementService(
        graph_repo=graph_repo,
        dashboard_emitter=SimpleNamespace(graph_mutation=lambda mutation: None),
    )
    dispatched: list[dict] = []

    monkeypatch.setattr(module, "get_session", lambda: _session_factory(session))

    async def _dispatch_task_ready(**kwargs):
        dispatched.append(kwargs)

    service._dispatch_task_ready = _dispatch_task_ready
    dependency_id = uuid4()

    await service.spawn_dynamic_task(
        run_id=uuid4(),
        parent_task_id=uuid4(),
        task=_DynamicTask(
            task_slug="child",
            instance_key="sample-1",
            description="child task",
            worker=TestWorker(name="worker", model=None),
            sandbox=TestSandbox(),
        ),
        depends_on=(dependency_id,),
    )

    assert dispatched == []
    assert graph_repo.added_edges[0]["source_task_id"] == dependency_id
