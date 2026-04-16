"""Unit tests for restart_task (Phase 1) and downstream invalidation (Phase 2).

Phase 1 tests cover the simple reset: terminal -> pending, outgoing edges
reset to EDGE_PENDING, task/ready emitted, and rejection of non-terminal
status. Phase 2 will add downstream invalidation assertions in this same
file once the cascade is implemented.
"""

from unittest.mock import patch
from uuid import uuid4

import pytest
from ergon_core.core.persistence.graph.status_conventions import (
    CANCELLED,
    COMPLETED,
    EDGE_INVALIDATED,
    EDGE_PENDING,
    EDGE_SATISFIED,
    FAILED,
    PENDING,
    RUNNING,
)
from ergon_core.core.runtime.errors.delegation_errors import TaskNotTerminalError
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.task_management_dto import RestartTaskCommand
from ergon_core.core.runtime.services.task_management_service import (
    TaskManagementService,
)
from sqlmodel import Session

from tests.state.mocks import FakeInngestClient

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


class TestRestartTaskBasic:
    """Phase 1: terminal -> PENDING with edge reset and task/ready dispatch."""

    @pytest.mark.parametrize("terminal_status", [COMPLETED, FAILED, CANCELLED])
    def test_restarts_from_terminal(self, session: Session, terminal_status: str):
        """restart_task resets a terminal node to PENDING."""
        fake = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = _add_node(repo, session, run_id, "target", status=terminal_status)

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            result = svc.restart_task(
                session,
                RestartTaskCommand(run_id=run_id, node_id=node.id),
            )

        assert result.old_status == terminal_status
        updated = repo.get_node(session, run_id=run_id, node_id=node.id)
        assert updated.status == PENDING

    def test_emits_task_ready(self, session: Session):
        """restart_task emits a task/ready Inngest event so the scheduler picks up the node."""
        fake = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = _add_node(repo, session, run_id, "target", status=COMPLETED)

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            svc.restart_task(
                session,
                RestartTaskCommand(run_id=run_id, node_id=node.id),
            )

        ready_events = fake.events_by_name("task/ready")
        assert len(ready_events) == 1
        assert ready_events[0].data["node_id"] == str(node.id)

    def test_resets_outgoing_edges(self, session: Session):
        """Outgoing SATISFIED / INVALIDATED edges are reset to EDGE_PENDING on restart."""
        fake = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        # Parent + two downstream nodes. Source node has two outgoing edges
        # in different states to prove both kinds get reset.
        parent = _add_node(repo, session, run_id, "manager", status=RUNNING)
        source = _add_node(
            repo, session, run_id, "src", status=COMPLETED, parent_node_id=parent.id, level=1
        )
        t_pending = _add_node(
            repo,
            session,
            run_id,
            "t-pending",
            status=PENDING,
            parent_node_id=parent.id,
            level=1,
        )
        t_cancelled = _add_node(
            repo,
            session,
            run_id,
            "t-cancelled",
            status=CANCELLED,
            parent_node_id=parent.id,
            level=1,
        )

        repo.add_edge(
            session,
            run_id,
            source_node_id=source.id,
            target_node_id=t_pending.id,
            status=EDGE_SATISFIED,
            meta=META,
        )
        repo.add_edge(
            session,
            run_id,
            source_node_id=source.id,
            target_node_id=t_cancelled.id,
            status=EDGE_INVALIDATED,
            meta=META,
        )
        session.commit()

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            svc.restart_task(
                session,
                RestartTaskCommand(run_id=run_id, node_id=source.id),
            )

        outgoing = repo.get_outgoing_edges(session, run_id=run_id, node_id=source.id)
        assert len(outgoing) == 2
        assert all(e.status == EDGE_PENDING for e in outgoing)

    def test_status_change_mutation_logged(self, session: Session):
        """restart_task writes a node.status_changed mutation (terminal -> pending)."""
        fake = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = _add_node(repo, session, run_id, "target", status=COMPLETED)
        seq_before = len(repo.get_mutations(session, run_id))

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            svc.restart_task(
                session,
                RestartTaskCommand(run_id=run_id, node_id=node.id),
            )

        new_mutations = repo.get_mutations(session, run_id)[seq_before:]
        status_changes = [m for m in new_mutations if m.mutation_type == "node.status_changed"]
        assert len(status_changes) == 1
        assert status_changes[0].old_value.status == COMPLETED  # type: ignore[union-attr]
        assert status_changes[0].new_value.status == PENDING  # type: ignore[union-attr]

    @pytest.mark.parametrize("live_status", [PENDING, RUNNING])
    def test_rejects_non_terminal(self, session: Session, live_status: str):
        """restart_task rejects PENDING and RUNNING nodes."""
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = _add_node(repo, session, run_id, "target", status=live_status)

        with pytest.raises(TaskNotTerminalError) as exc_info:
            svc.restart_task(
                session,
                RestartTaskCommand(run_id=run_id, node_id=node.id),
            )
        assert exc_info.value.node_id == node.id
        assert exc_info.value.current_status == live_status

    def test_no_outgoing_edges_still_works(self, session: Session):
        """A leaf node (no outgoing edges) restarts cleanly."""
        fake = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = _add_node(repo, session, run_id, "leaf", status=FAILED)

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            result = svc.restart_task(
                session,
                RestartTaskCommand(run_id=run_id, node_id=node.id),
            )

        assert result.old_status == FAILED
        assert result.invalidated_node_ids == []
        updated = repo.get_node(session, run_id=run_id, node_id=node.id)
        assert updated.status == PENDING
