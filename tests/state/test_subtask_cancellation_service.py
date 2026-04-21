"""SubtaskCancellationService unit tests.

Verifies recursive cascade cancel: the full descendant subtree is
cancelled in one pass, non-terminal nodes are cancelled, terminal
nodes are skipped.
"""

from uuid import uuid4

from ergon_core.core.persistence.graph.status_conventions import (
    CANCELLED,
    COMPLETED,
    FAILED,
    PENDING,
    RUNNING,
)
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.subtask_cancellation_service import (
    SubtaskCancellationService,
)
from sqlmodel import Session

META = MutationMeta(actor="test", reason="test-setup")


async def _add_node(
    repo: WorkflowGraphRepository,
    session: Session,
    run_id,
    key: str,
    *,
    status: str = PENDING,
    instance_key: str = "inst-0",
    parent_node_id=None,
    level: int = 0,
):
    """Helper to create a graph node for test setup."""
    return await repo.add_node(
        session,
        run_id,
        task_key=key,
        instance_key=instance_key,
        description=f"node {key}",
        status=status,
        parent_node_id=parent_node_id,
        level=level,
        meta=META,
    )


class TestCancelOrphans:
    """Tests for cancel_orphans — engine-driven cascade cancel."""

    async def test_cancels_non_terminal_children(self, session: Session):
        """Non-terminal children are cancelled, terminal ones are skipped."""
        repo = WorkflowGraphRepository()
        svc = SubtaskCancellationService(graph_repo=repo)
        run_id = uuid4()
        definition_id = uuid4()

        parent = await _add_node(repo, session, run_id, "parent", status=CANCELLED)
        pending_child = await _add_node(
            repo,
            session,
            run_id,
            "pending-child",
            status=PENDING,
            parent_node_id=parent.id,
            level=1,
        )
        running_child = await _add_node(
            repo,
            session,
            run_id,
            "running-child",
            status=RUNNING,
            parent_node_id=parent.id,
            level=1,
        )
        await _add_node(
            repo,
            session,
            run_id,
            "completed-child",
            status=COMPLETED,
            parent_node_id=parent.id,
            level=1,
        )
        await _add_node(
            repo,
            session,
            run_id,
            "failed-child",
            status=FAILED,
            parent_node_id=parent.id,
            level=1,
        )

        result = await svc.cancel_orphans(
            session,
            run_id=run_id,
            definition_id=definition_id,
            parent_node_id=parent.id,
            cause="parent_terminal",
        )

        assert len(result.cancelled_node_ids) == 2
        assert pending_child.id in result.cancelled_node_ids
        assert running_child.id in result.cancelled_node_ids

        assert len(result.events_to_emit) == 2
        event_node_ids = {e.node_id for e in result.events_to_emit}
        assert pending_child.id in event_node_ids
        assert running_child.id in event_node_ids

        for event in result.events_to_emit:
            assert event.cause == "parent_terminal"
            assert event.definition_id == definition_id

        # Verify DB state
        for nid in [pending_child.id, running_child.id]:
            node = repo.get_node(session, run_id=run_id, node_id=nid)
            assert node.status == CANCELLED

    async def test_empty_children_is_noop(self, session: Session):
        """A parent with no children produces an empty result."""
        repo = WorkflowGraphRepository()
        svc = SubtaskCancellationService(graph_repo=repo)
        run_id = uuid4()
        definition_id = uuid4()

        parent = await _add_node(repo, session, run_id, "lonely-parent", status=CANCELLED)

        result = await svc.cancel_orphans(
            session,
            run_id=run_id,
            definition_id=definition_id,
            parent_node_id=parent.id,
            cause="parent_terminal",
        )

        assert result.cancelled_node_ids == []
        assert result.events_to_emit == []

    async def test_recursive_cancels_grandchildren(self, session: Session):
        """cancel_orphans walks the full subtree — grandchildren are cancelled too."""
        repo = WorkflowGraphRepository()
        svc = SubtaskCancellationService(graph_repo=repo)
        run_id = uuid4()
        definition_id = uuid4()

        parent = await _add_node(repo, session, run_id, "parent", status=CANCELLED)
        child = await _add_node(
            repo,
            session,
            run_id,
            "child",
            status=PENDING,
            parent_node_id=parent.id,
            level=1,
        )
        grandchild = await _add_node(
            repo,
            session,
            run_id,
            "grandchild",
            status=PENDING,
            parent_node_id=child.id,
            level=2,
        )

        result = await svc.cancel_orphans(
            session,
            run_id=run_id,
            definition_id=definition_id,
            parent_node_id=parent.id,
            cause="parent_terminal",
        )

        # Both child and grandchild are cancelled in one pass
        assert len(result.cancelled_node_ids) == 2
        assert child.id in result.cancelled_node_ids
        assert grandchild.id in result.cancelled_node_ids

        # Verify DB state
        gc_node = repo.get_node(session, run_id=run_id, node_id=grandchild.id)
        assert gc_node.status == CANCELLED

    async def test_deep_tree_cancelled_fully(self, session: Session):
        """A 4-level deep tree is cancelled in a single call."""
        repo = WorkflowGraphRepository()
        svc = SubtaskCancellationService(graph_repo=repo)
        run_id = uuid4()
        definition_id = uuid4()

        root = await _add_node(repo, session, run_id, "root", status=CANCELLED)
        l1 = await _add_node(
            repo, session, run_id, "L1", status=RUNNING, parent_node_id=root.id, level=1
        )
        l2 = await _add_node(
            repo, session, run_id, "L2", status=PENDING, parent_node_id=l1.id, level=2
        )
        l3 = await _add_node(
            repo, session, run_id, "L3", status=PENDING, parent_node_id=l2.id, level=3
        )

        result = await svc.cancel_orphans(
            session,
            run_id=run_id,
            definition_id=definition_id,
            parent_node_id=root.id,
            cause="parent_terminal",
        )

        assert set(result.cancelled_node_ids) == {l1.id, l2.id, l3.id}
        assert len(result.events_to_emit) == 3

    async def test_skips_terminal_but_walks_past_them(self, session: Session):
        """A completed child's non-terminal grandchild is still cancelled."""
        repo = WorkflowGraphRepository()
        svc = SubtaskCancellationService(graph_repo=repo)
        run_id = uuid4()
        definition_id = uuid4()

        parent = await _add_node(repo, session, run_id, "parent", status=CANCELLED)
        completed_child = await _add_node(
            repo,
            session,
            run_id,
            "completed-child",
            status=COMPLETED,
            parent_node_id=parent.id,
            level=1,
        )
        # Grandchild under the completed child — still needs cancelling
        orphan_grandchild = await _add_node(
            repo,
            session,
            run_id,
            "orphan-gc",
            status=RUNNING,
            parent_node_id=completed_child.id,
            level=2,
        )

        result = await svc.cancel_orphans(
            session,
            run_id=run_id,
            definition_id=definition_id,
            parent_node_id=parent.id,
            cause="parent_terminal",
        )

        # completed_child is skipped (already terminal)
        # but orphan_grandchild is still cancelled
        assert len(result.cancelled_node_ids) == 1
        assert orphan_grandchild.id in result.cancelled_node_ids
