"""Tests for the WorkerContext facade — spawn_task path + containment guard.

Covers three scenarios that exercise the facade methods landed in
PR 9 Tasks 2-3:

- ``spawn_task`` round-trips through ``TaskManagementService.spawn_dynamic_task``
  and writes only to ``run_graph_nodes`` (never ``experiment_definition_tasks``).
- The spawned dynamic node inflates correctly through
  ``WorkflowGraphRepository.node`` (is_dynamic=True + correct task_slug).
- ``cancel_task`` enforces containment via ``_assert_descendant``,
  raising ``ContainmentViolation`` for non-descendants and routing
  to ``_task_mgmt`` only for legitimate descendants.

The other facade methods (``refine_task``, ``restart_task``, ``subtasks``,
``descendants``, ``get_task``) call kwarg-form service methods that the
service layer doesn't expose yet — tests for those land in a future PR.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from ergon_core.api.benchmark.task import Task
from ergon_core.api.errors import ContainmentViolation
from ergon_core.api.worker.context import WorkerContext
from ergon_core.api.worker.results import SpawnedTaskHandle
from ergon_core.core.application.graph.models import RunGraphNodeView
from ergon_core.core.application.graph.repository import WorkflowGraphRepository
from ergon_core.core.application.tasks import inspection as inspection_module
from ergon_core.core.application.tasks import management as management_module
from ergon_core.core.application.tasks.inspection import TaskInspectionService
from ergon_core.core.application.tasks.management import TaskManagementService
from ergon_core.core.persistence.definitions.models import ExperimentDefinitionTask
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.tests.unit.runtime._test_workers import EchoSandbox, EchoWorker
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


# ---------------------------------------------------------------------------
# Helpers (mirroring the in-memory SQLite pattern from
# test_spawn_dynamic_task.py).
# ---------------------------------------------------------------------------


class _SessionContext:
    """Context-manager wrapper that yields a single Session unchanged.

    Replaces ``get_session()`` so the service code under test reuses the
    test's in-memory session instead of opening a new one.
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


def _seed_node(
    session: Session,
    *,
    run_id: UUID,
    slug: str,
    parent_node_id: UUID | None = None,
    level: int = 0,
    status: str = "RUNNING",
) -> RunGraphNode:
    node = RunGraphNode(
        run_id=run_id,
        instance_key="sample-1",
        task_slug=slug,
        description=f"Task {slug}",
        status=status,
        is_dynamic=False,
        parent_node_id=parent_node_id,
        level=level,
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


def _patch_get_session(monkeypatch: pytest.MonkeyPatch, session: Session) -> None:
    """Make every ``get_session()`` call inside the service modules return
    the test session, so service writes/reads stay in the SQLite memdb the
    test set up.
    """

    def ctx_factory() -> _SessionContext:
        return _SessionContext(session)

    monkeypatch.setattr(management_module, "get_session", ctx_factory)
    monkeypatch.setattr(inspection_module, "get_session", ctx_factory)


def _build_context(
    *,
    run_id: UUID,
    task_id: UUID,
    task_mgmt: object,
    task_inspect: object,
) -> WorkerContext:
    return WorkerContext._for_job(
        run_id=run_id,
        task_id=task_id,
        execution_id=uuid4(),
        definition_id=None,
        sandbox_id="sandbox-test",
        node_id=task_id,
        task_mgmt=task_mgmt,
        task_inspect=task_inspect,
        resource_repo=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_task_via_worker_context_does_not_write_definition_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """spawn_task through the facade writes one run-graph row, zero definition rows."""

    session = _make_session()
    run_id = uuid4()
    parent = _seed_node(session, run_id=run_id, slug="parent")
    _patch_get_session(monkeypatch, session)

    task_mgmt = TaskManagementService(dashboard_emitter=MagicMock())
    task_inspect = TaskInspectionService()
    context = _build_context(
        run_id=run_id,
        task_id=parent.id,
        task_mgmt=task_mgmt,
        task_inspect=task_inspect,
    )

    nodes_before = session.exec(select(RunGraphNode)).all()
    defs_before = session.exec(select(ExperimentDefinitionTask)).all()
    assert len(nodes_before) == 1  # only the parent

    handle = await context.spawn_task(_make_task())

    nodes_after = session.exec(select(RunGraphNode)).all()
    defs_after = session.exec(select(ExperimentDefinitionTask)).all()

    # Exactly one new run-graph row, no new definition rows.
    assert len(nodes_after) == len(nodes_before) + 1
    assert len(defs_after) == len(defs_before) == 0

    new_node = session.exec(
        select(RunGraphNode).where(
            RunGraphNode.run_id == run_id,
            RunGraphNode.task_slug == "child",
        )
    ).one()

    assert new_node.is_dynamic is True
    assert new_node.parent_node_id == parent.id
    assert new_node.task_json["task_slug"] == "child"
    assert isinstance(handle, SpawnedTaskHandle)
    assert handle.task_id == new_node.id


@pytest.mark.asyncio
async def test_spawned_task_inflates_through_graph_repo_node(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The spawned dynamic node round-trips through graph_repo.node as is_dynamic=True."""

    session = _make_session()
    run_id = uuid4()
    parent = _seed_node(session, run_id=run_id, slug="parent")
    _patch_get_session(monkeypatch, session)

    task_mgmt = TaskManagementService(dashboard_emitter=MagicMock())
    task_inspect = TaskInspectionService()
    context = _build_context(
        run_id=run_id,
        task_id=parent.id,
        task_mgmt=task_mgmt,
        task_inspect=task_inspect,
    )

    handle = await context.spawn_task(_make_task())

    graph_repo = WorkflowGraphRepository()
    view = await graph_repo.node(session, run_id=run_id, task_id=handle.task_id)

    assert isinstance(view, RunGraphNodeView)
    assert view.is_dynamic is True
    assert view.task_id == handle.task_id
    assert view.task.task_slug == "child"


@pytest.mark.asyncio
async def test_worker_context_cancel_raises_on_non_descendant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cancel_task enforces containment: non-descendant → ContainmentViolation."""

    session = _make_session()
    run_id = uuid4()
    root = _seed_node(session, run_id=run_id, slug="root")
    child = _seed_node(
        session,
        run_id=run_id,
        slug="child",
        parent_node_id=root.id,
        level=1,
    )
    sibling = _seed_node(session, run_id=run_id, slug="sibling")  # peer of root, no parent
    _patch_get_session(monkeypatch, session)

    # Real inspection service so _assert_descendant queries the actual graph;
    # mocked management service so we can assert the rejection path doesn't
    # call into it (and to avoid wiring the still-evolving cancel kwarg form).
    task_mgmt = MagicMock()
    task_mgmt.cancel_task = AsyncMock(return_value=None)
    task_inspect = TaskInspectionService()

    context = _build_context(
        run_id=run_id,
        task_id=root.id,
        task_mgmt=task_mgmt,
        task_inspect=task_inspect,
    )

    # Non-descendant: ContainmentViolation, service never called.
    with pytest.raises(ContainmentViolation) as excinfo:
        await context.cancel_task(sibling.id)

    assert excinfo.value.parent_task_id == root.id
    assert excinfo.value.target_task_id == sibling.id
    task_mgmt.cancel_task.assert_not_called()

    # Descendant: routes to the (mocked) service exactly once with kwargs.
    await context.cancel_task(child.id)

    task_mgmt.cancel_task.assert_awaited_once_with(
        run_id=run_id,
        task_id=child.id,
        reason="",
    )
