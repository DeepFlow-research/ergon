"""Test 6 — manager_decision cancel (operator-initiated cancellation).

Tests that cancelling a PENDING node writes CANCELLED status and a WAL
entry. This is expected to pass with current code — cancellation is
already implemented. No xfail needed.

If this were asserting SampleRecord status assertions that aren't yet wired,
it would need xfail; but the simple node-level cancel works today.
"""

import pytest
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import SampleGraphEdge, SampleGraphMutation, SampleGraphNode
from ergon_core.core.application.runtime.status import CANCELLED
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord
from ergon_core.core.application.runtime.models import MutationMeta
from ergon_core.core.application.runtime.graph_repository import RuntimeGraphRepository
from sqlmodel import select

from tests.integration.propagation._helpers import (
    assert_cross_cutting_invariants,
    assert_wal_has_status,
    get_node_status,
    make_experiment_definition,
    make_node,
    make_run,
)

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Cleanup helper
# ---------------------------------------------------------------------------


def _cleanup_run(sample_id, defn_id) -> None:  # type: ignore[no-untyped-def]
    with get_session() as session:
        for mut in session.exec(
            select(SampleGraphMutation).where(SampleGraphMutation.sample_id == sample_id)
        ).all():
            session.delete(mut)
        for edge in session.exec(select(SampleGraphEdge).where(SampleGraphEdge.sample_id == sample_id)).all():
            session.delete(edge)
        for nd in session.exec(select(SampleGraphNode).where(SampleGraphNode.sample_id == sample_id)).all():
            session.delete(nd)
        run_row = session.get(SampleRecord, sample_id)
        if run_row is not None:
            session.delete(run_row)
        defn_row = session.get(ExperimentDefinition, defn_id)
        if defn_row is not None:
            session.delete(defn_row)
        session.commit()


# ---------------------------------------------------------------------------
# Test 6: operator-initiated cancel of a PENDING node
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_6_manager_decision_cancel_pending_node() -> None:
    """An operator (manager) cancels a PENDING node.

    The node transitions to CANCELLED and a WAL entry is written.
    This tests direct graph-repo cancellation — no propagation event needed.
    Expected to pass with current code (cancellation is implemented).
    """
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        node_a = make_node(session, run.id, task_slug="cancel-target", status="pending")
        sample_id = run.id
        defn_id = defn.id
        node_a_id = node_a.task_id
        session.commit()

    try:
        graph_repo = RuntimeGraphRepository()

        # First stamp PENDING into the WAL so the WAL invariant holds.
        with get_session() as session:
            await graph_repo.update_node_status(
                session,
                sample_id=sample_id,
                task_id=node_a_id,
                new_status=TaskExecutionStatus.PENDING,
                meta=MutationMeta(actor="test:setup", reason="test setup: node pending"),
            )
            session.commit()

        # Simulate manager/operator decision to cancel.
        with get_session() as session:
            await graph_repo.update_node_status(
                session,
                sample_id=sample_id,
                task_id=node_a_id,
                new_status=CANCELLED,
                meta=MutationMeta(
                    actor="manager:operator",
                    reason="manager_decision: operator cancelled task",
                ),
            )
            session.commit()

        with get_session() as session:
            status = get_node_status(session, node_a_id)
            assert status == CANCELLED, (
                f"Expected node to be CANCELLED after operator cancel; got {status!r}"
            )
            assert_wal_has_status(
                session,
                node_a_id,
                CANCELLED,
                cause_contains="manager_decision",
            )

        with get_session() as session:
            assert_cross_cutting_invariants(session, sample_id)

    finally:
        _cleanup_run(sample_id, defn_id)


@pytest.mark.asyncio
async def test_6b_cancel_does_not_affect_already_terminal_node() -> None:
    """Cancelling an already COMPLETED node must be a no-op (only_if_not_terminal).

    The existing ``only_if_not_terminal`` guard in RuntimeGraphRepository
    prevents overwriting a terminal node. This tests that behaviour directly.
    Expected to pass with current code.
    """
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        node_a = make_node(session, run.id, task_slug="already-completed", status="completed")
        sample_id = run.id
        defn_id = defn.id
        node_a_id = node_a.task_id
        session.commit()

    try:
        graph_repo = RuntimeGraphRepository()

        with get_session() as session:
            # Stamp COMPLETED into WAL
            await graph_repo.update_node_status(
                session,
                sample_id=sample_id,
                task_id=node_a_id,
                new_status=TaskExecutionStatus.COMPLETED,
                meta=MutationMeta(actor="test:setup", reason="test setup: node completed"),
            )
            session.commit()

        # Attempt to cancel — should be a no-op (only_if_not_terminal=True)
        with get_session() as session:
            applied = await graph_repo.update_node_status(
                session,
                sample_id=sample_id,
                task_id=node_a_id,
                new_status=CANCELLED,
                meta=MutationMeta(actor="test:operator", reason="late cancel attempt"),
                only_if_not_terminal=True,
            )
            session.commit()

        assert not applied, "Expected cancel to be rejected for already-COMPLETED node"

        with get_session() as session:
            status = get_node_status(session, node_a_id)
            assert status == TaskExecutionStatus.COMPLETED, (
                f"Node should still be COMPLETED after rejected cancel; got {status!r}"
            )

        with get_session() as session:
            assert_cross_cutting_invariants(session, sample_id)

    finally:
        _cleanup_run(sample_id, defn_id)
