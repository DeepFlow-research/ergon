"""Edge-case propagation tests.

EC-1: fan-in race under failure → BLOCKED, not CANCELLED.
EC-2: duplicate task/ready idempotency. Expected to pass with current code.
"""

import pytest
from ergon_core.core.persistence.graph.models import SampleGraphEdge, SampleGraphNode
from ergon_core.core.application.runtime.status import BLOCKED, CANCELLED
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import SampleStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord
from ergon_core.core.application.runtime.models import MutationMeta
from ergon_core.core.application.runtime.graph_repository import RuntimeGraphRepository
from ergon_core.core.application.runtime.orchestration import PropagateTaskCompletionCommand
from ergon_core.core.application.runtime.sample_lifecycle import WorkflowService
from sqlmodel import select

from tests.integration.propagation._helpers import (
    assert_cross_cutting_invariants,
    delete_typed_sample_wal,
    assert_wal_has_status,
    get_node_status,
    make_edge,
    make_node,
    make_run,
)

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Cleanup helper
# ---------------------------------------------------------------------------


def _cleanup_run(sample_id) -> None:  # type: ignore[no-untyped-def]
    with get_session() as session:
        delete_typed_sample_wal(session, sample_id)
        for edge in session.exec(
            select(SampleGraphEdge).where(SampleGraphEdge.sample_id == sample_id)
        ).all():
            session.delete(edge)
        nodes = list(
            session.exec(
                select(SampleGraphNode).where(SampleGraphNode.sample_id == sample_id)
            ).all()
        )
        remaining = {node.task_id: node for node in nodes}
        while remaining:
            parent_ids = {
                node.parent_task_id
                for node in remaining.values()
                if node.parent_task_id is not None
            }
            leaves = [node for node in remaining.values() if node.task_id not in parent_ids]
            for node in leaves:
                session.delete(node)
                remaining.pop(node.task_id)
            session.flush()
        run_row = session.get(SampleRecord, sample_id)
        if run_row is not None:
            session.delete(run_row)
        session.commit()


# ---------------------------------------------------------------------------
# EC-1: fan-in: one dep fails, other completes — target must be BLOCKED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ec1_fan_in_one_dep_fails_target_blocked() -> None:
    """Fan-in race: two dependencies A and B → C.

    A fails; B completes. C must become BLOCKED because one of its
    dependencies failed — not CANCELLED (which was the old behaviour).

    Topology:
        A ──┐
             ├──► C
        B ──┘

    Execution order:
      1. A fails → propagate_failure from A → edge A→C invalidated.
      2. B completes → propagate from B → B's edge to C is satisfied.
      3. C cannot start (one dep failed) → must be BLOCKED.
    """
    with get_session() as session:
        run = make_run(session)
        node_a = make_node(session, run.id, task_slug="fan-a", status="running")
        node_b = make_node(session, run.id, task_slug="fan-b", status="running")
        node_c = make_node(session, run.id, task_slug="fan-c", status="pending")
        make_edge(session, run.id, source_task_id=node_a.task_id, target_task_id=node_c.task_id)
        make_edge(session, run.id, source_task_id=node_b.task_id, target_task_id=node_c.task_id)
        sample_id = run.id
        node_a_id = node_a.task_id
        node_b_id = node_b.task_id
        node_c_id = node_c.task_id
        session.commit()

    try:
        graph_repo = RuntimeGraphRepository()
        with get_session() as session:
            await graph_repo.update_node_status(
                session,
                sample_id=sample_id,
                task_id=node_a_id,
                new_status=TaskExecutionStatus.FAILED,
                meta=MutationMeta(actor="test:setup", reason="test: A failed"),
            )
            await graph_repo.update_node_status(
                session,
                sample_id=sample_id,
                task_id=node_b_id,
                new_status=TaskExecutionStatus.COMPLETED,
                meta=MutationMeta(actor="test:setup", reason="test: B completed"),
            )
            session.commit()

        svc = WorkflowService()

        # Propagate A's failure first
        await svc.propagate_failure(
            PropagateTaskCompletionCommand(
                sample_id=sample_id,
                task_id=node_a_id,
                execution_id=node_a_id,
            )
        )

        # Then propagate B's completion — B is done but A already failed C
        await svc.propagate(
            PropagateTaskCompletionCommand(
                sample_id=sample_id,
                task_id=node_b_id,
                execution_id=node_b_id,
            )
        )

        with get_session() as session:
            c_status = get_node_status(session, node_c_id)
            # C must be BLOCKED (not CANCELLED) when one dep failed (fan-in)
            assert c_status == BLOCKED, (
                f"Expected C to be BLOCKED when one dep failed (fan-in); got {c_status!r}"
            )
            assert_wal_has_status(session, node_c_id, BLOCKED)

        # SampleRecord must remain EXECUTING — the run is stuck, not over
        with get_session() as session:
            run_row = session.get(SampleRecord, sample_id)
            assert run_row is not None
            assert run_row.status == SampleStatus.EXECUTING, (
                f"SampleRecord must remain EXECUTING while C is blocked; got {run_row.status!r}"
            )

        with get_session() as session:
            assert_cross_cutting_invariants(session, sample_id)

    finally:
        _cleanup_run(sample_id)


# ---------------------------------------------------------------------------
# EC-2: duplicate ready / idempotency — calling propagate twice is safe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ec2_duplicate_propagate_is_idempotent() -> None:
    """Calling propagate() twice for the same completed node is idempotent.

    The second call must not crash, must not flip the node back to PENDING,
    and must not corrupt the WAL. This tests the only_if_not_terminal guard.

    Expected to PASS with current code — no xfail.
    """
    with get_session() as session:
        run = make_run(session)
        node_a = make_node(session, run.id, task_slug="idem-a", status="running")
        node_b = make_node(session, run.id, task_slug="idem-b", status="pending")
        make_edge(session, run.id, source_task_id=node_a.task_id, target_task_id=node_b.task_id)
        sample_id = run.id
        node_a_id = node_a.task_id
        node_b_id = node_b.task_id
        session.commit()

    try:
        graph_repo = RuntimeGraphRepository()
        with get_session() as session:
            await graph_repo.update_node_status(
                session,
                sample_id=sample_id,
                task_id=node_a_id,
                new_status=TaskExecutionStatus.RUNNING,
                meta=MutationMeta(actor="test:setup", reason="test setup"),
            )
            session.commit()

        svc = WorkflowService()

        command = PropagateTaskCompletionCommand(
            sample_id=sample_id,
            task_id=node_a_id,
            execution_id=node_a_id,
        )

        # First propagation
        await svc.propagate(command)

        with get_session() as session:
            a_status = get_node_status(session, node_a_id)
            assert a_status == TaskExecutionStatus.COMPLETED, (
                f"Expected A to be COMPLETED after first propagate; got {a_status!r}"
            )

        # Second propagation of the same node — must be safe
        await svc.propagate(command)

        with get_session() as session:
            a_status_after = get_node_status(session, node_a_id)
            assert a_status_after == TaskExecutionStatus.COMPLETED, (
                f"Expected A to remain COMPLETED after duplicate propagate; got {a_status_after!r}"
            )
            # B should still be in its post-first-propagate state (PENDING/ready)
            b_status = get_node_status(session, node_b_id)
            # B should be PENDING (was activated by first propagation) or COMPLETED
            # — the key invariant is it's not FAILED or CANCELLED from a spurious call
            assert b_status not in {
                TaskExecutionStatus.FAILED,
                CANCELLED,
            }, f"B status corrupted by duplicate propagate; got {b_status!r}"

        with get_session() as session:
            assert_cross_cutting_invariants(session, sample_id)

    finally:
        _cleanup_run(sample_id)
