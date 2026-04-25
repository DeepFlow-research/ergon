"""Tests for BLOCKED propagation semantics."""

import pytest
from sqlmodel import select

from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.graph.status_conventions import BLOCKED, CANCELLED
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import RunRecord
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.orchestration_dto import PropagateTaskCompletionCommand
from ergon_core.core.runtime.services.task_propagation_service import TaskPropagationService

from tests.integration.propagation._helpers import (
    assert_wal_has_status,
    assert_cross_cutting_invariants,
    get_node_status,
    make_experiment_definition,
    make_edge,
    make_node,
    make_run,
    seed_linear_chain,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Cleanup helper (shared across this module)
# ---------------------------------------------------------------------------


def _cleanup_run(run_id, defn_id) -> None:  # type: ignore[no-untyped-def]
    """Remove all rows created by a test, in FK-safe order."""
    with get_session() as session:
        for mut in session.exec(
            select(RunGraphMutation).where(RunGraphMutation.run_id == run_id)
        ).all():
            session.delete(mut)
        for edge in session.exec(select(RunGraphEdge).where(RunGraphEdge.run_id == run_id)).all():
            session.delete(edge)
        for nd in session.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).all():
            session.delete(nd)
        run_row = session.get(RunRecord, run_id)
        if run_row is not None:
            session.delete(run_row)
        defn_row = session.get(ExperimentDefinition, defn_id)
        if defn_row is not None:
            session.delete(defn_row)
        session.commit()


# ---------------------------------------------------------------------------
# Test 3: 3-task linear chain — B fails, C becomes BLOCKED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_3_failure_cascade_successor_blocked() -> None:
    """Linear chain A→B→C. B fails. C must become BLOCKED, not CANCELLED.

    Also asserts:
    - RunRecord does not transition to FAILED (the run stays EXECUTING).
    - WAL entry for C records BLOCKED status.
    """
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        # A seeded completed; B seeded pending; C pending — WAL stamps below set definitive statuses
        node_a, node_b, node_c = seed_linear_chain(
            session,
            run.id,
            ["task-a", "task-b", "task-c"],
            first_status="completed",
            rest_status="pending",
        )
        run_id = run.id
        defn_id = defn.id
        node_a_id = node_a.id
        node_b_id = node_b.id
        node_c_id = node_c.id
        session.commit()

    try:
        # Stamp WAL entries for setup state
        graph_repo = WorkflowGraphRepository()
        with get_session() as session:
            await graph_repo.update_node_status(
                session,
                run_id=run_id,
                node_id=node_a_id,
                new_status=TaskExecutionStatus.COMPLETED,
                meta=MutationMeta(actor="test:setup", reason="test: A completed"),
            )
            await graph_repo.update_node_status(
                session,
                run_id=run_id,
                node_id=node_b_id,
                new_status=TaskExecutionStatus.FAILED,
                meta=MutationMeta(actor="test:setup", reason="test: B failed"),
            )
            session.commit()

        # Propagate failure from B
        svc = TaskPropagationService()
        await svc.propagate_failure(
            PropagateTaskCompletionCommand(
                run_id=run_id,
                definition_id=defn_id,
                task_id=node_b_id,
                execution_id=node_b_id,
                node_id=node_b_id,
            )
        )

        with get_session() as session:
            # C must be BLOCKED, not CANCELLED
            c_status = get_node_status(session, node_c_id)
            assert c_status == BLOCKED, f"Expected C to be BLOCKED after B failed; got {c_status!r}"
            # WAL must have a BLOCKED entry for C
            assert_wal_has_status(session, node_c_id, BLOCKED)

        # RunRecord must remain EXECUTING — propagation of a single failure must not flip the run
        # to FAILED while successor nodes are in the BLOCKED (operator-awaiting) state.
        with get_session() as session:
            run_row = session.get(RunRecord, run_id)
            assert run_row is not None
            assert run_row.status == RunStatus.EXECUTING, (
                f"RunRecord must remain EXECUTING while blocked successors await operator; "
                f"got {run_row.status!r}"
            )

        with get_session() as session:
            assert_cross_cutting_invariants(session, run_id)

    finally:
        _cleanup_run(run_id, defn_id)


# ---------------------------------------------------------------------------
# Test 7: parent-failure → pending children become BLOCKED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_7_parent_failure_children_blocked() -> None:
    """Parent task fails. Its PENDING child successors become BLOCKED, not CANCELLED or FAILED.

    Uses a 2-level structure: parent_node → [child_a, child_b] via edges.
    parent_node is a static (parent_node_id=None) node so the propagation
    logic treats its successors as static workflow nodes that should be
    auto-managed (not left pending for a manager).
    """
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        parent_node = make_node(session, run.id, task_slug="parent", status="running")
        child_a = make_node(session, run.id, task_slug="child-a", status="pending")
        child_b = make_node(session, run.id, task_slug="child-b", status="pending")
        # child_c is already RUNNING — propagation must NOT interrupt it
        child_c = make_node(session, run.id, task_slug="child-c", status="running")
        # child_d is already COMPLETED — it is terminal and must not be overwritten
        child_d = make_node(session, run.id, task_slug="child-d", status="completed")
        make_edge(session, run.id, source_node_id=parent_node.id, target_node_id=child_a.id)
        make_edge(session, run.id, source_node_id=parent_node.id, target_node_id=child_b.id)
        make_edge(session, run.id, source_node_id=parent_node.id, target_node_id=child_c.id)
        make_edge(session, run.id, source_node_id=parent_node.id, target_node_id=child_d.id)
        run_id = run.id
        defn_id = defn.id
        parent_node_id = parent_node.id
        child_a_id = child_a.id
        child_b_id = child_b.id
        child_c_id = child_c.id
        child_d_id = child_d.id
        session.commit()

    try:
        graph_repo = WorkflowGraphRepository()
        with get_session() as session:
            await graph_repo.update_node_status(
                session,
                run_id=run_id,
                node_id=parent_node_id,
                new_status=TaskExecutionStatus.FAILED,
                meta=MutationMeta(actor="test:setup", reason="test: parent failed"),
            )
            await graph_repo.update_node_status(
                session,
                run_id=run_id,
                node_id=child_c_id,
                new_status=TaskExecutionStatus.RUNNING,
                meta=MutationMeta(actor="test:setup", reason="test: child-c already running"),
            )
            await graph_repo.update_node_status(
                session,
                run_id=run_id,
                node_id=child_d_id,
                new_status=TaskExecutionStatus.COMPLETED,
                meta=MutationMeta(actor="test:setup", reason="test: child-d already completed"),
            )
            session.commit()

        svc = TaskPropagationService()
        await svc.propagate_failure(
            PropagateTaskCompletionCommand(
                run_id=run_id,
                definition_id=defn_id,
                task_id=parent_node_id,
                execution_id=parent_node_id,
                node_id=parent_node_id,
            )
        )

        with get_session() as session:
            for child_id, slug in [(child_a_id, "child-a"), (child_b_id, "child-b")]:
                child_status = get_node_status(session, child_id)
                assert child_status == BLOCKED, (
                    f"Expected {slug} to be BLOCKED after parent failed; got {child_status!r}"
                )
                assert_wal_has_status(session, child_id, BLOCKED)

            # RUNNING child must not be interrupted by parent failure
            child_c_status = get_node_status(session, child_c_id)
            assert child_c_status == TaskExecutionStatus.RUNNING, (
                f"Expected child-c to remain RUNNING; propagation must not interrupt a running task; "
                f"got {child_c_status!r}"
            )

            # COMPLETED child is already terminal — must not be overwritten
            child_d_status = get_node_status(session, child_d_id)
            assert child_d_status == TaskExecutionStatus.COMPLETED, (
                f"Expected child-d to remain COMPLETED; terminal nodes must not be overwritten; "
                f"got {child_d_status!r}"
            )

        # RunRecord must remain EXECUTING — not auto-failed by propagation
        with get_session() as session:
            run_row = session.get(RunRecord, run_id)
            assert run_row is not None
            assert run_row.status == RunStatus.EXECUTING, (
                f"RunRecord must remain EXECUTING while blocked children await operator; "
                f"got {run_row.status!r}"
            )

        with get_session() as session:
            assert_cross_cutting_invariants(session, run_id)

    finally:
        _cleanup_run(run_id, defn_id)


# ---------------------------------------------------------------------------
# Test 10: BLOCKED propagates transitively (A→B→C, A fails → B and C both blocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_10_blocked_propagates_transitively() -> None:
    """Linear chain A→B→C. A fails. Both B and C must become BLOCKED.

    This tests that BLOCKED propagates through the graph transitively,
    not just one level deep.
    """
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        node_a, node_b, node_c = seed_linear_chain(
            session,
            run.id,
            ["task-a", "task-b", "task-c"],
            first_status="running",
            rest_status="pending",
        )
        run_id = run.id
        defn_id = defn.id
        node_a_id = node_a.id
        node_b_id = node_b.id
        node_c_id = node_c.id
        session.commit()

    try:
        graph_repo = WorkflowGraphRepository()
        with get_session() as session:
            await graph_repo.update_node_status(
                session,
                run_id=run_id,
                node_id=node_a_id,
                new_status=TaskExecutionStatus.FAILED,
                meta=MutationMeta(actor="test:setup", reason="test: A failed"),
            )
            session.commit()

        svc = TaskPropagationService()
        await svc.propagate_failure(
            PropagateTaskCompletionCommand(
                run_id=run_id,
                definition_id=defn_id,
                task_id=node_a_id,
                execution_id=node_a_id,
                node_id=node_a_id,
            )
        )

        with get_session() as session:
            # B is a direct successor of A — must be BLOCKED
            b_status = get_node_status(session, node_b_id)
            assert b_status == BLOCKED, f"Expected B to be BLOCKED after A failed; got {b_status!r}"
            assert_wal_has_status(session, node_b_id, BLOCKED)

            # C is a transitive successor — must also become BLOCKED
            c_status = get_node_status(session, node_c_id)
            assert c_status == BLOCKED, (
                f"Expected C to be BLOCKED (transitively) after A failed; got {c_status!r}"
            )
            assert_wal_has_status(session, node_c_id, BLOCKED)

        # RunRecord must remain EXECUTING — not auto-failed by propagation
        with get_session() as session:
            run_row = session.get(RunRecord, run_id)
            assert run_row is not None
            assert run_row.status == RunStatus.EXECUTING, (
                f"RunRecord must remain EXECUTING while blocked successors await operator; "
                f"got {run_row.status!r}"
            )

        with get_session() as session:
            assert_cross_cutting_invariants(session, run_id)

    finally:
        _cleanup_run(run_id, defn_id)


# ---------------------------------------------------------------------------
# Test 12: RUNNING successor is NOT interrupted when an unrelated dep fails
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_12_running_successor_not_interrupted() -> None:
    """A→B. B is already RUNNING when A fails. B must NOT be marked blocked/cancelled.

    A RUNNING task must finish on its own terms. The propagation system
    must not interrupt it by writing BLOCKED or CANCELLED over a RUNNING node.
    """
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        node_a = make_node(session, run.id, task_slug="task-a", status="failed")
        node_b = make_node(session, run.id, task_slug="task-b", status="running")
        make_edge(session, run.id, source_node_id=node_a.id, target_node_id=node_b.id)
        run_id = run.id
        defn_id = defn.id
        node_a_id = node_a.id
        node_b_id = node_b.id
        session.commit()

    try:
        graph_repo = WorkflowGraphRepository()
        with get_session() as session:
            await graph_repo.update_node_status(
                session,
                run_id=run_id,
                node_id=node_a_id,
                new_status=TaskExecutionStatus.FAILED,
                meta=MutationMeta(actor="test:setup", reason="test: A failed"),
            )
            await graph_repo.update_node_status(
                session,
                run_id=run_id,
                node_id=node_b_id,
                new_status=TaskExecutionStatus.RUNNING,
                meta=MutationMeta(actor="test:setup", reason="test: B already running"),
            )
            session.commit()

        svc = TaskPropagationService()
        await svc.propagate_failure(
            PropagateTaskCompletionCommand(
                run_id=run_id,
                definition_id=defn_id,
                task_id=node_a_id,
                execution_id=node_a_id,
                node_id=node_a_id,
            )
        )

        with get_session() as session:
            b_status = get_node_status(session, node_b_id)
            # B is RUNNING — propagation must not overwrite it with BLOCKED or CANCELLED
            assert b_status == TaskExecutionStatus.RUNNING, (
                f"Expected B to remain RUNNING while executing; "
                f"propagation must not interrupt a running task. Got {b_status!r}"
            )

        # RunRecord must remain EXECUTING — B is still running, the run is not over
        with get_session() as session:
            run_row = session.get(RunRecord, run_id)
            assert run_row is not None
            assert run_row.status == RunStatus.EXECUTING, (
                f"RunRecord must remain EXECUTING while B is still running; got {run_row.status!r}"
            )

        with get_session() as session:
            assert_cross_cutting_invariants(session, run_id)

    finally:
        _cleanup_run(run_id, defn_id)
