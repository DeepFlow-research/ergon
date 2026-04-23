"""Test 1 — single-task happy path.

A single-node run completes successfully. The graph node must reach
COMPLETED status and the RunRecord must stay non-failed.

Expected to PASS with current production code (no xfail).
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlmodel import select

from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.shared.db import get_engine, get_session
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import RunRecord
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.orchestration_dto import PropagateTaskCompletionCommand
from ergon_core.core.runtime.services.task_propagation_service import TaskPropagationService

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
# Connectivity guard
# ---------------------------------------------------------------------------


def _probe_db_reachable() -> bool:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


@pytest.fixture(scope="session", autouse=True)
def _skip_if_db_unreachable() -> None:
    if not _probe_db_reachable():
        pytest.skip("Database unreachable — skipping propagation integration tests")


# ---------------------------------------------------------------------------
# Cleanup helpers
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
# Test 1: single task happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_1_single_task_happy_path() -> None:
    """A single completed task node transitions to COMPLETED and WAL is written.

    This exercises the graph-native v2 propagation path through
    TaskPropagationService.propagate(). Expected to pass with current code.
    """
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        node_a = make_node(session, run.id, task_slug="task-a", status="running")
        run_id = run.id
        defn_id = defn.id
        node_a_id = node_a.id
        session.commit()

    try:
        # Stamp RUNNING into the WAL so the WAL invariant check passes.
        graph_repo = WorkflowGraphRepository()
        with get_session() as session:
            await graph_repo.update_node_status(
                session,
                run_id=run_id,
                node_id=node_a_id,
                new_status=TaskExecutionStatus.RUNNING,
                meta=MutationMeta(actor="test:setup", reason="test setup: running"),
            )
            session.commit()

        # Propagate completion directly through the service.
        svc = TaskPropagationService()
        await svc.propagate(
            PropagateTaskCompletionCommand(
                run_id=run_id,
                definition_id=defn_id,
                task_id=node_a_id,
                execution_id=node_a_id,
                node_id=node_a_id,
            )
        )

        # --- Assertions ---
        with get_session() as session:
            status = get_node_status(session, node_a_id)
            assert status == TaskExecutionStatus.COMPLETED, (
                f"Expected node to be COMPLETED, got {status!r}"
            )
            assert_wal_has_status(session, node_a_id, "completed")

        # RunRecord must not be FAILED after single-task happy-path completion.
        with get_session() as session:
            run_row = session.get(RunRecord, run_id)
            assert run_row is not None
            assert run_row.status != RunStatus.FAILED, (
                f"RunRecord should not be FAILED; got {run_row.status!r}"
            )

        with get_session() as session:
            assert_cross_cutting_invariants(session, run_id)
    finally:
        _cleanup_run(run_id, defn_id)
