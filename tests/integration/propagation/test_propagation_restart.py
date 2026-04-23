"""Test 8 — restart semantics stub.

This test is a stub for the restart / operator_unblock semantics that
will be implemented in Step 6. It is marked xfail(strict=True) because
the production code does not yet implement:
  - operator_unblock: transition a BLOCKED node back to PENDING
  - restart: re-run a FAILED or BLOCKED node from scratch

When Step 6 is complete, this test should be expanded and un-xfailed.
"""
import pytest
from sqlmodel import select

from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.graph.status_conventions import BLOCKED
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import RunRecord
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.orchestration_dto import PropagateTaskCompletionCommand
from ergon_core.core.runtime.services.task_propagation_service import TaskPropagationService

from tests.integration.propagation._helpers import (
    assert_wal_has_status,
    get_node_status,
    make_experiment_definition,
    make_edge,
    make_node,
    make_run,
)

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Cleanup helper
# ---------------------------------------------------------------------------


def _cleanup_run(run_id, defn_id) -> None:  # type: ignore[no-untyped-def]
    with get_session() as session:
        for mut in session.exec(
            select(RunGraphMutation).where(RunGraphMutation.run_id == run_id)
        ).all():
            session.delete(mut)
        for edge in session.exec(
            select(RunGraphEdge).where(RunGraphEdge.run_id == run_id)
        ).all():
            session.delete(edge)
        for nd in session.exec(
            select(RunGraphNode).where(RunGraphNode.run_id == run_id)
        ).all():
            session.delete(nd)
        run_row = session.get(RunRecord, run_id)
        if run_row is not None:
            session.delete(run_row)
        defn_row = session.get(ExperimentDefinition, defn_id)
        if defn_row is not None:
            session.delete(defn_row)
        session.commit()


# ---------------------------------------------------------------------------
# Test 8: restart / operator_unblock (Step 6 semantics)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Restart semantics not yet implemented — "
        "operator_unblock (BLOCKED → PENDING) is a Step 6 feature"
    ),
)
@pytest.mark.asyncio
async def test_8_operator_unblock_transitions_blocked_to_pending() -> None:
    """An operator can unblock a BLOCKED node, transitioning it back to PENDING.

    Scenario:
      1. A→B chain. A fails → B becomes BLOCKED.
      2. Operator retries / fixes A (A transitions to COMPLETED).
      3. operator_unblock is called on B → B becomes PENDING.
      4. Propagation resumes: B becomes READY for execution.

    This is a stub — the ``operator_unblock`` function/service call
    below is intentionally referencing a function that does not yet exist
    (``TaskPropagationService.operator_unblock``). The test will xfail
    at import/collection time because of the missing attribute OR at
    assertion time because B stays BLOCKED.
    """
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        node_a = make_node(session, run.id, task_slug="task-a-failed", status="failed")
        node_b = make_node(session, run.id, task_slug="task-b-blocked", status="blocked")
        make_edge(session, run.id, source_node_id=node_a.id, target_node_id=node_b.id)
        session.commit()

    try:
        graph_repo = WorkflowGraphRepository()

        with get_session() as session:
            await graph_repo.update_node_status(
                session,
                run_id=run.id,
                node_id=node_a.id,
                new_status=TaskExecutionStatus.FAILED,
                meta=MutationMeta(actor="test:setup", reason="test: A failed"),
            )
            await graph_repo.update_node_status(
                session,
                run_id=run.id,
                node_id=node_b.id,
                new_status=BLOCKED,
                meta=MutationMeta(actor="test:setup", reason="test: B blocked by A failure"),
            )
            session.commit()

        # Step 6 will add this method. It doesn't exist yet — xfail covers the AttributeError.
        svc = TaskPropagationService()
        await svc.operator_unblock(  # type: ignore[attr-defined]  # Step 6: not implemented yet
            run_id=run.id,
            node_id=node_b.id,
            reason="operator: unblocking B after A was retried",
        )

        with get_session() as session:
            b_status = get_node_status(session, node_b.id)
            assert b_status == TaskExecutionStatus.PENDING, (
                f"Expected B to be PENDING after operator_unblock; got {b_status!r}"
            )
            assert_wal_has_status(session, node_b.id, "pending")

    finally:
        _cleanup_run(run.id, defn.id)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Restart of FAILED node not yet implemented — "
        "re-running a FAILED task is a Step 6 feature"
    ),
)
@pytest.mark.asyncio
async def test_8b_restart_failed_node_re_enters_running() -> None:
    """A FAILED node can be restarted, transitioning back through PENDING → RUNNING.

    This is a stub — the restart semantics are Step 6 work. The test
    asserts the FAILED node becomes RUNNING after a restart call, which
    will xfail until the implementation exists.
    """
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        node_a = make_node(session, run.id, task_slug="task-a-to-restart", status="failed")
        session.commit()

    try:
        graph_repo = WorkflowGraphRepository()
        with get_session() as session:
            await graph_repo.update_node_status(
                session,
                run_id=run.id,
                node_id=node_a.id,
                new_status=TaskExecutionStatus.FAILED,
                meta=MutationMeta(actor="test:setup", reason="test: A failed"),
            )
            session.commit()

        # Step 6 will add this method.
        svc = TaskPropagationService()
        await svc.restart_node(  # type: ignore[attr-defined]  # Step 6: not implemented yet
            run_id=run.id,
            node_id=node_a.id,
            reason="operator: restarting A",
        )

        with get_session() as session:
            a_status = get_node_status(session, node_a.id)
            assert a_status == TaskExecutionStatus.PENDING, (
                f"Expected A to be PENDING after restart; got {a_status!r}"
            )

    finally:
        _cleanup_run(run.id, defn.id)
