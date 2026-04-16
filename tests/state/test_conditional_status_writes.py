"""Tests for the only_if_not_terminal conditional guard on update_node_status.

The conditional write is the single invariant that closes all race conditions
in the cascade cancellation system (RFC §4.4). Every concurrent path —
cancel vs complete, cascade vs cascade, manager cancel vs engine cascade —
resolves to "first writer wins" via this guard.
"""

from uuid import uuid4

import pytest
from sqlmodel import Session

from ergon_core.core.persistence.graph.status_conventions import (
    CANCELLED,
    COMPLETED,
    FAILED,
    PENDING,
    RUNNING,
    TERMINAL_STATUSES,
)
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository

META = MutationMeta(actor="test", reason="test")


class TestConditionalStatusWrites:
    def test_guard_blocks_write_on_completed_node(self, session: Session) -> None:
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        node = repo.add_node(
            session, run_id,
            task_key="t1", instance_key="i0", description="test",
            status=COMPLETED, meta=META,
        )
        result = repo.update_node_status(
            session,
            run_id=run_id, node_id=node.id, new_status=CANCELLED,
            meta=META, only_if_not_terminal=True,
        )
        assert result is False

    def test_guard_blocks_write_on_failed_node(self, session: Session) -> None:
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        node = repo.add_node(
            session, run_id,
            task_key="t1", instance_key="i0", description="test",
            status=FAILED, meta=META,
        )
        result = repo.update_node_status(
            session,
            run_id=run_id, node_id=node.id, new_status=CANCELLED,
            meta=META, only_if_not_terminal=True,
        )
        assert result is False

    def test_guard_blocks_write_on_cancelled_node(self, session: Session) -> None:
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        node = repo.add_node(
            session, run_id,
            task_key="t1", instance_key="i0", description="test",
            status=CANCELLED, meta=META,
        )
        result = repo.update_node_status(
            session,
            run_id=run_id, node_id=node.id, new_status=COMPLETED,
            meta=META, only_if_not_terminal=True,
        )
        assert result is False

    def test_guard_allows_write_on_running_node(self, session: Session) -> None:
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        node = repo.add_node(
            session, run_id,
            task_key="t1", instance_key="i0", description="test",
            status=RUNNING, meta=META,
        )
        result = repo.update_node_status(
            session,
            run_id=run_id, node_id=node.id, new_status=CANCELLED,
            meta=META, only_if_not_terminal=True,
        )
        assert result is True
        refreshed = repo.get_node(session, run_id=run_id, node_id=node.id)
        assert refreshed.status == CANCELLED

    def test_unconditional_write_still_works(self, session: Session) -> None:
        """Without the guard, writes proceed even on terminal nodes."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        node = repo.add_node(
            session, run_id,
            task_key="t1", instance_key="i0", description="test",
            status=COMPLETED, meta=META,
        )
        # Default only_if_not_terminal=False: unconditional
        result = repo.update_node_status(
            session,
            run_id=run_id, node_id=node.id, new_status=FAILED,
            meta=META,
        )
        assert result is True

    def test_guard_does_not_emit_mutation_on_blocked_write(self, session: Session) -> None:
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        node = repo.add_node(
            session, run_id,
            task_key="t1", instance_key="i0", description="test",
            status=COMPLETED, meta=META,
        )
        mutations_before = repo.get_mutations(session, run_id)
        count_before = len(mutations_before)

        repo.update_node_status(
            session,
            run_id=run_id, node_id=node.id, new_status=CANCELLED,
            meta=META, only_if_not_terminal=True,
        )
        mutations_after = repo.get_mutations(session, run_id)
        assert len(mutations_after) == count_before
