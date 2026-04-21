"""Dep-failure cascade tests: static vs dynamic subtask behaviour.

Static workflow nodes (parent_node_id=None) are auto-cancelled when a
dependency fails. Dynamic subtasks (parent_node_id set) stay PENDING so
the manager can adapt — retry, cancel, or re-plan.
"""

from uuid import uuid4

from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.runtime.execution.propagation import on_task_completed_or_failed
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from sqlmodel import Session

META = MutationMeta(actor="test", reason="dep-failure-cascade-test")


async def _add_node(
    repo: WorkflowGraphRepository,
    session: Session,
    run_id,
    slug: str,
    *,
    status: str = TaskExecutionStatus.PENDING,
    parent_node_id=None,
    level: int = 0,
):
    return await repo.add_node(
        session,
        run_id,
        task_slug=slug,
        instance_key="inst-0",
        description=f"node {slug}",
        status=status,
        parent_node_id=parent_node_id,
        level=level,
        meta=META,
    )


class TestStaticNodeAutoCancel:
    """Static workflow nodes (parent_node_id=None) are auto-cancelled on dep failure."""

    async def test_failure_cancels_static_downstream(self, session: Session):
        """A -> B, A -> C (all static). A fails. B and C should be CANCELLED."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        a = await _add_node(repo, session, run_id, "A", status=TaskExecutionStatus.FAILED)
        b = await _add_node(repo, session, run_id, "B")
        c = await _add_node(repo, session, run_id, "C")

        await repo.add_edge(
            session,
            run_id,
            source_node_id=a.id,
            target_node_id=b.id,
            status="pending",
            meta=META,
        )
        await repo.add_edge(
            session,
            run_id,
            source_node_id=a.id,
            target_node_id=c.id,
            status="pending",
            meta=META,
        )
        session.flush()

        _ready, invalidated = await on_task_completed_or_failed(
            session,
            run_id,
            a.id,
            TaskExecutionStatus.FAILED,
            graph_repo=repo,
        )

        assert set(invalidated) == {b.id, c.id}

        b_row = session.get(RunGraphNode, b.id)
        c_row = session.get(RunGraphNode, c.id)
        assert b_row is not None and b_row.status == "cancelled"
        assert c_row is not None and c_row.status == "cancelled"

    async def test_failure_returns_invalidated_list(self, session: Session):
        """Invalidated list matches the downstream static nodes."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        a = await _add_node(repo, session, run_id, "A", status=TaskExecutionStatus.FAILED)
        b = await _add_node(repo, session, run_id, "B")
        await repo.add_edge(
            session,
            run_id,
            source_node_id=a.id,
            target_node_id=b.id,
            status="pending",
            meta=META,
        )
        session.flush()

        _ready, invalidated = await on_task_completed_or_failed(
            session,
            run_id,
            a.id,
            TaskExecutionStatus.FAILED,
            graph_repo=repo,
        )

        assert invalidated == [b.id]


class TestDynamicSubtaskNoAutoCancel:
    """Dynamic subtasks (parent_node_id set) stay PENDING on dep failure."""

    async def test_failure_does_not_cancel_managed_subtask(self, session: Session):
        """A -> B where B is a managed subtask (has parent_node_id).
        A fails. B should remain PENDING — the manager decides what to do."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        manager = await _add_node(
            repo, session, run_id, "manager", status=TaskExecutionStatus.RUNNING
        )
        a = await _add_node(
            repo,
            session,
            run_id,
            "A",
            status=TaskExecutionStatus.FAILED,
            parent_node_id=manager.id,
            level=1,
        )
        b = await _add_node(
            repo,
            session,
            run_id,
            "B",
            status=TaskExecutionStatus.PENDING,
            parent_node_id=manager.id,
            level=1,
        )

        await repo.add_edge(
            session,
            run_id,
            source_node_id=a.id,
            target_node_id=b.id,
            status="pending",
            meta=META,
        )
        session.flush()

        _ready, invalidated = await on_task_completed_or_failed(
            session,
            run_id,
            a.id,
            TaskExecutionStatus.FAILED,
            graph_repo=repo,
        )

        # B should NOT be in invalidated — it's manager-owned
        assert b.id not in invalidated

        b_row = session.get(RunGraphNode, b.id)
        assert b_row is not None
        assert b_row.status == TaskExecutionStatus.PENDING

    async def test_failure_still_invalidates_edges_for_managed_subtask(self, session: Session):
        """Even though B stays PENDING, the edge A->B should be INVALIDATED."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        manager = await _add_node(
            repo, session, run_id, "manager", status=TaskExecutionStatus.RUNNING
        )
        a = await _add_node(
            repo,
            session,
            run_id,
            "A",
            status=TaskExecutionStatus.FAILED,
            parent_node_id=manager.id,
            level=1,
        )
        b = await _add_node(
            repo,
            session,
            run_id,
            "B",
            status=TaskExecutionStatus.PENDING,
            parent_node_id=manager.id,
            level=1,
        )

        edge = await repo.add_edge(
            session,
            run_id,
            source_node_id=a.id,
            target_node_id=b.id,
            status="pending",
            meta=META,
        )
        session.flush()

        await on_task_completed_or_failed(
            session,
            run_id,
            a.id,
            TaskExecutionStatus.FAILED,
            graph_repo=repo,
        )

        from ergon_core.core.persistence.graph.models import RunGraphEdge

        edge_row = session.get(RunGraphEdge, edge.id)
        assert edge_row is not None
        assert edge_row.status == "invalidated"

    async def test_mixed_static_and_dynamic_targets(self, session: Session):
        """A -> B (dynamic), A -> C (static). A fails.
        B stays PENDING (managed). C is CANCELLED (no supervisor)."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        manager = await _add_node(
            repo, session, run_id, "manager", status=TaskExecutionStatus.RUNNING
        )
        a = await _add_node(
            repo,
            session,
            run_id,
            "A",
            status=TaskExecutionStatus.FAILED,
            parent_node_id=manager.id,
            level=1,
        )
        # B is a managed subtask
        b = await _add_node(
            repo,
            session,
            run_id,
            "B",
            parent_node_id=manager.id,
            level=1,
        )
        # C is a static workflow node (no parent)
        c = await _add_node(repo, session, run_id, "C")

        await repo.add_edge(
            session,
            run_id,
            source_node_id=a.id,
            target_node_id=b.id,
            status="pending",
            meta=META,
        )
        await repo.add_edge(
            session,
            run_id,
            source_node_id=a.id,
            target_node_id=c.id,
            status="pending",
            meta=META,
        )
        session.flush()

        _ready, invalidated = await on_task_completed_or_failed(
            session,
            run_id,
            a.id,
            TaskExecutionStatus.FAILED,
            graph_repo=repo,
        )

        # Only C (static) should be invalidated
        assert c.id in invalidated
        assert b.id not in invalidated

        b_row = session.get(RunGraphNode, b.id)
        c_row = session.get(RunGraphNode, c.id)
        assert b_row is not None and b_row.status == TaskExecutionStatus.PENDING
        assert c_row is not None and c_row.status == "cancelled"

    async def test_completion_still_unblocks_managed_subtask(self, session: Session):
        """A -> B (dynamic). A completes. B should become READY — success
        path is unchanged regardless of parent_node_id."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        manager = await _add_node(
            repo, session, run_id, "manager", status=TaskExecutionStatus.RUNNING
        )
        a = await _add_node(
            repo,
            session,
            run_id,
            "A",
            status=TaskExecutionStatus.COMPLETED,
            parent_node_id=manager.id,
            level=1,
        )
        b = await _add_node(
            repo,
            session,
            run_id,
            "B",
            status=TaskExecutionStatus.PENDING,
            parent_node_id=manager.id,
            level=1,
        )

        await repo.add_edge(
            session,
            run_id,
            source_node_id=a.id,
            target_node_id=b.id,
            status="pending",
            meta=META,
        )
        session.flush()

        ready, _invalidated = await on_task_completed_or_failed(
            session,
            run_id,
            a.id,
            TaskExecutionStatus.COMPLETED,
            graph_repo=repo,
        )

        assert b.id in ready
