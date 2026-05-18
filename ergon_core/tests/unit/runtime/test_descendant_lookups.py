"""Tests for WorkflowGraphRepository.descendants_by_parent and
TaskInspectionService.descendant_ids.
"""

from uuid import UUID, uuid4

import pytest
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.application.graph.repository import WorkflowGraphRepository
from ergon_core.core.application.tasks import inspection as inspection_module
from ergon_core.core.application.tasks.inspection import TaskInspectionService
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _node(
    session: Session,
    *,
    run_id: UUID,
    slug: str,
    parent_task_id: UUID | None = None,
    status: str = "PENDING",
) -> RunGraphNode:
    node = RunGraphNode(
        run_id=run_id,
        instance_key="sample-1",
        task_slug=slug,
        description=f"Task {slug}",
        is_dynamic=False,
        status=status,
        parent_task_id=parent_task_id,
    )
    session.add(node)
    session.flush()
    return node


# ---------------------------------------------------------------------------
# WorkflowGraphRepository.descendants_by_parent tests
# ---------------------------------------------------------------------------


class TestDescendantsByParent:
    def test_returns_direct_and_transitive_children(self) -> None:
        """root → child1, root → child2, child1 → grandchild: 3 rows returned."""
        session = _make_session()
        run_id = uuid4()
        repo = WorkflowGraphRepository()

        root = _node(session, run_id=run_id, slug="root")
        child1 = _node(session, run_id=run_id, slug="child1", parent_task_id=root.task_id)
        child2 = _node(session, run_id=run_id, slug="child2", parent_task_id=root.task_id)
        grandchild = _node(session, run_id=run_id, slug="grandchild", parent_task_id=child1.task_id)
        session.commit()

        rows = repo.descendants_by_parent(session, run_id=run_id, root_task_id=root.task_id)
        result_ids = {row.task_id for row in rows}

        assert result_ids == {child1.task_id, child2.task_id, grandchild.task_id}

    def test_does_not_include_root_or_sibling(self) -> None:
        """root and an unrelated sibling at run root level are excluded."""
        session = _make_session()
        run_id = uuid4()
        repo = WorkflowGraphRepository()

        root = _node(session, run_id=run_id, slug="root")
        child1 = _node(session, run_id=run_id, slug="child1", parent_task_id=root.task_id)
        sibling = _node(session, run_id=run_id, slug="sibling")  # no parent_task_id
        session.commit()

        rows = repo.descendants_by_parent(session, run_id=run_id, root_task_id=root.task_id)
        result_ids = {row.task_id for row in rows}

        assert root.task_id not in result_ids
        assert sibling.task_id not in result_ids
        assert child1.task_id in result_ids

    def test_returns_empty_when_root_has_no_children(self) -> None:
        """A leaf node returns ()."""
        session = _make_session()
        run_id = uuid4()
        repo = WorkflowGraphRepository()

        leaf = _node(session, run_id=run_id, slug="leaf")
        session.commit()

        rows = repo.descendants_by_parent(session, run_id=run_id, root_task_id=leaf.task_id)
        assert rows == ()

    def test_depth_greater_than_two(self) -> None:
        """Recursion works past depth 2: root → A → B → C → D."""
        session = _make_session()
        run_id = uuid4()
        repo = WorkflowGraphRepository()

        root = _node(session, run_id=run_id, slug="root")
        a = _node(session, run_id=run_id, slug="a", parent_task_id=root.task_id)
        b = _node(session, run_id=run_id, slug="b", parent_task_id=a.task_id)
        c = _node(session, run_id=run_id, slug="c", parent_task_id=b.task_id)
        d = _node(session, run_id=run_id, slug="d", parent_task_id=c.task_id)
        session.commit()

        rows = repo.descendants_by_parent(session, run_id=run_id, root_task_id=root.task_id)
        result_ids = {row.task_id for row in rows}

        assert result_ids == {a.task_id, b.task_id, c.task_id, d.task_id}

    def test_cross_run_isolation(self) -> None:
        """Nodes from a different run_id are not included."""
        session = _make_session()
        run_id = uuid4()
        other_run_id = uuid4()
        repo = WorkflowGraphRepository()

        root = _node(session, run_id=run_id, slug="root")
        child = _node(session, run_id=run_id, slug="child", parent_task_id=root.task_id)
        # A node in another run that happens to point at root.task_id as parent
        other = _node(session, run_id=other_run_id, slug="other", parent_task_id=root.task_id)
        session.commit()

        rows = repo.descendants_by_parent(session, run_id=run_id, root_task_id=root.task_id)
        result_ids = {row.task_id for row in rows}

        assert result_ids == {child.task_id}
        assert other.task_id not in result_ids


# ---------------------------------------------------------------------------
# TaskInspectionService.descendant_ids tests
# ---------------------------------------------------------------------------


class TestTaskInspectionServiceDescendantIds:
    async def test_returns_same_set_as_repository(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """descendant_ids returns a frozenset matching descendants_by_parent."""
        session = _make_session()
        run_id = uuid4()

        root = _node(session, run_id=run_id, slug="root")
        child1 = _node(session, run_id=run_id, slug="child1", parent_task_id=root.task_id)
        child2 = _node(session, run_id=run_id, slug="child2", parent_task_id=root.task_id)
        grandchild = _node(session, run_id=run_id, slug="grandchild", parent_task_id=child1.task_id)
        session.commit()

        # Patch get_session in the inspection module to return the test session
        monkeypatch.setattr(inspection_module, "get_session", lambda: session)

        repo = WorkflowGraphRepository()
        svc = TaskInspectionService(graph_repo=repo)

        result = await svc.descendant_ids(run_id=run_id, root_task_id=root.task_id)

        assert isinstance(result, frozenset)
        assert result == frozenset({child1.task_id, child2.task_id, grandchild.task_id})

    async def test_returns_empty_frozenset_when_no_children(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns frozenset() when root has no children."""
        session = _make_session()
        run_id = uuid4()

        leaf = _node(session, run_id=run_id, slug="leaf")
        session.commit()

        monkeypatch.setattr(inspection_module, "get_session", lambda: session)

        repo = WorkflowGraphRepository()
        svc = TaskInspectionService(graph_repo=repo)

        result = await svc.descendant_ids(run_id=run_id, root_task_id=leaf.task_id)

        assert result == frozenset()

    async def test_depth_greater_than_two(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """descendant_ids resolves all nodes in a chain of depth > 2."""
        session = _make_session()
        run_id = uuid4()

        root = _node(session, run_id=run_id, slug="root")
        a = _node(session, run_id=run_id, slug="a", parent_task_id=root.task_id)
        b = _node(session, run_id=run_id, slug="b", parent_task_id=a.task_id)
        c = _node(session, run_id=run_id, slug="c", parent_task_id=b.task_id)
        session.commit()

        monkeypatch.setattr(inspection_module, "get_session", lambda: session)

        repo = WorkflowGraphRepository()
        svc = TaskInspectionService(graph_repo=repo)

        result = await svc.descendant_ids(run_id=run_id, root_task_id=root.task_id)

        assert result == frozenset({a.task_id, b.task_id, c.task_id})
