"""SubtaskCancellationService unit tests.

Verifies single-level cascade cancel: non-terminal children are
cancelled, terminal children are skipped, grandchildren are untouched.
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


def _add_node(
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
    return repo.add_node(
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

    def test_cancels_non_terminal_children(self, session: Session):
        """Non-terminal children are cancelled, terminal ones are skipped."""
        repo = WorkflowGraphRepository()
        svc = SubtaskCancellationService(graph_repo=repo)
        run_id = uuid4()
        definition_id = uuid4()

        parent = _add_node(repo, session, run_id, "parent", status=CANCELLED)
        pending_child = _add_node(
            repo,
            session,
            run_id,
            "pending-child",
            status=PENDING,
            parent_node_id=parent.id,
            level=1,
        )
        running_child = _add_node(
            repo,
            session,
            run_id,
            "running-child",
            status=RUNNING,
            parent_node_id=parent.id,
            level=1,
        )
        _add_node(
            repo,
            session,
            run_id,
            "completed-child",
            status=COMPLETED,
            parent_node_id=parent.id,
            level=1,
        )
        _add_node(
            repo,
            session,
            run_id,
            "failed-child",
            status=FAILED,
            parent_node_id=parent.id,
            level=1,
        )

        result = svc.cancel_orphans(
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

    def test_empty_children_is_noop(self, session: Session):
        """A parent with no children produces an empty result."""
        repo = WorkflowGraphRepository()
        svc = SubtaskCancellationService(graph_repo=repo)
        run_id = uuid4()
        definition_id = uuid4()

        parent = _add_node(repo, session, run_id, "lonely-parent", status=CANCELLED)

        result = svc.cancel_orphans(
            session,
            run_id=run_id,
            definition_id=definition_id,
            parent_node_id=parent.id,
            cause="parent_terminal",
        )

        assert result.cancelled_node_ids == []
        assert result.events_to_emit == []

    def test_only_direct_children_not_grandchildren(self, session: Session):
        """cancel_orphans is single-level — grandchildren are untouched."""
        repo = WorkflowGraphRepository()
        svc = SubtaskCancellationService(graph_repo=repo)
        run_id = uuid4()
        definition_id = uuid4()

        parent = _add_node(repo, session, run_id, "parent", status=CANCELLED)
        child = _add_node(
            repo,
            session,
            run_id,
            "child",
            status=PENDING,
            parent_node_id=parent.id,
            level=1,
        )
        grandchild = _add_node(
            repo,
            session,
            run_id,
            "grandchild",
            status=PENDING,
            parent_node_id=child.id,
            level=2,
        )

        result = svc.cancel_orphans(
            session,
            run_id=run_id,
            definition_id=definition_id,
            parent_node_id=parent.id,
            cause="parent_terminal",
        )

        # Only child is cancelled, not grandchild
        assert len(result.cancelled_node_ids) == 1
        assert child.id in result.cancelled_node_ids

        # Grandchild still pending (cascade would happen via separate Inngest event)
        gc_node = repo.get_node(session, run_id=run_id, node_id=grandchild.id)
        assert gc_node.status == PENDING
