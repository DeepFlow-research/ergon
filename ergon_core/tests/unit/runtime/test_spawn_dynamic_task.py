"""Tests for TaskManagementService.spawn_dynamic_task.

Verifies the dynamic-spawn write path:

- Exactly one row inserted into run_graph_nodes with is_dynamic=True and
  the full Task snapshot in task_json.
- Zero rows inserted into experiment_definition_tasks.
- Optional depends_on creates the dependency edge in run_graph_edges.
- Returned SpawnedTaskHandle.task_id matches the inserted node's id.
"""

from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from ergon_core.api.benchmark.task import Task
from ergon_core.api.worker.results import SpawnedTaskHandle
from ergon_core.core.application.tasks import management as management_module
from ergon_core.core.application.tasks.management import TaskManagementService
from ergon_core.core.persistence.definitions.models import ExperimentDefinitionTask
from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphNode
from ergon_core.tests.unit.runtime._test_workers import EchoSandbox, EchoWorker
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _SessionContext:
    """Context-manager wrapper that yields the wrapped session unchanged.

    The test injects this in place of get_session() so the management
    code's ``with get_session() as session:`` block reuses the same
    in-memory SQLite session that the test seeds and inspects.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *args: object) -> None:
        return None


def _make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _seed_parent(session: Session, *, run_id: UUID) -> RunGraphNode:
    parent = RunGraphNode(
        run_id=run_id,
        instance_key="sample-1",
        task_slug="parent",
        description="Parent task",
        status="RUNNING",
        is_dynamic=False,
        parent_node_id=None,
        level=0,
    )
    session.add(parent)
    session.commit()
    return parent


def _seed_other(session: Session, *, run_id: UUID, slug: str) -> RunGraphNode:
    node = RunGraphNode(
        run_id=run_id,
        instance_key="sample-1",
        task_slug=slug,
        description=f"Task {slug}",
        status="PENDING",
        is_dynamic=False,
        parent_node_id=None,
        level=0,
    )
    session.add(node)
    session.commit()
    return node


def _make_task() -> Task:
    return Task(
        task_slug="child",
        instance_key="sample-1",
        description="spawned child",
        worker=EchoWorker(name="echo", model=None),
        sandbox=EchoSandbox(),
        evaluators=(),
    )


def _service(session: Session, monkeypatch: pytest.MonkeyPatch) -> TaskManagementService:
    """Build a TaskManagementService that talks to the test session."""
    monkeypatch.setattr(
        management_module,
        "get_session",
        lambda: _SessionContext(session),
    )
    return TaskManagementService(dashboard_emitter=MagicMock())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_dynamic_task_inserts_dynamic_node_with_task_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single is_dynamic=True row is written with the full Task snapshot."""
    session = _make_session()
    run_id = uuid4()
    parent = _seed_parent(session, run_id=run_id)
    svc = _service(session, monkeypatch)

    nodes_before = session.exec(select(RunGraphNode)).all()
    assert len(nodes_before) == 1  # only the parent

    task = _make_task()
    handle = await svc.spawn_dynamic_task(
        run_id=run_id,
        parent_task_id=parent.id,
        task=task,
    )

    new_node = session.exec(
        select(RunGraphNode).where(
            RunGraphNode.run_id == run_id,
            RunGraphNode.task_slug == "child",
        )
    ).one()

    assert new_node.is_dynamic is True
    assert new_node.parent_node_id == parent.id
    assert new_node.level == parent.level + 1
    assert new_node.status == "pending"

    # task_json carries the full serialized Task, including subclass
    # discriminators on worker/sandbox.
    assert new_node.task_json["task_slug"] == "child"
    assert new_node.task_json["instance_key"] == "sample-1"
    assert new_node.task_json["description"] == "spawned child"
    assert new_node.task_json["_type"].endswith(":Task")
    assert new_node.task_json["worker"]["_type"].endswith(":EchoWorker")
    assert new_node.task_json["sandbox"]["_type"].endswith(":EchoSandbox")

    # Returned handle points at the inserted row.
    assert isinstance(handle, SpawnedTaskHandle)
    assert handle.task_id == new_node.id


@pytest.mark.asyncio
async def test_spawn_dynamic_task_does_not_write_definition_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """experiment_definition_tasks count is unchanged before/after spawn."""
    session = _make_session()
    run_id = uuid4()
    parent = _seed_parent(session, run_id=run_id)
    svc = _service(session, monkeypatch)

    defs_before = session.exec(select(ExperimentDefinitionTask)).all()

    await svc.spawn_dynamic_task(
        run_id=run_id,
        parent_task_id=parent.id,
        task=_make_task(),
    )

    defs_after = session.exec(select(ExperimentDefinitionTask)).all()
    assert len(defs_before) == len(defs_after) == 0


@pytest.mark.asyncio
async def test_spawn_dynamic_task_creates_dependency_edge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """depends_on=(other,) writes a run_graph_edges row source=other, target=new."""
    session = _make_session()
    run_id = uuid4()
    parent = _seed_parent(session, run_id=run_id)
    other = _seed_other(session, run_id=run_id, slug="other")
    svc = _service(session, monkeypatch)

    handle = await svc.spawn_dynamic_task(
        run_id=run_id,
        parent_task_id=parent.id,
        task=_make_task(),
        depends_on=(other.id,),
    )

    edges = session.exec(select(RunGraphEdge).where(RunGraphEdge.run_id == run_id)).all()
    assert len(edges) == 1
    assert edges[0].source_node_id == other.id
    assert edges[0].target_node_id == handle.task_id


@pytest.mark.asyncio
async def test_spawn_dynamic_task_handle_matches_inserted_row_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SpawnedTaskHandle.task_id is the new node's id (UUID)."""
    session = _make_session()
    run_id = uuid4()
    parent = _seed_parent(session, run_id=run_id)
    svc = _service(session, monkeypatch)

    handle = await svc.spawn_dynamic_task(
        run_id=run_id,
        parent_task_id=parent.id,
        task=_make_task(),
    )

    inserted_ids = frozenset(
        row.id
        for row in session.exec(
            select(RunGraphNode).where(
                RunGraphNode.run_id == run_id,
                RunGraphNode.task_slug == "child",
            )
        ).all()
    )

    assert isinstance(handle.task_id, UUID)
    assert handle.task_id in inserted_ids
    assert inserted_ids == frozenset({handle.task_id})
