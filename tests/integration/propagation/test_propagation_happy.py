"""Test 1 — single-task happy path.

A single-node run completes successfully. The graph node must reach
COMPLETED status and the SampleRecord must stay non-failed.

Expected to PASS with current production code (no xfail).
"""

import pytest
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import (
    SampleGraphEdge,
    SampleGraphMutation,
    SampleGraphNode,
)
from ergon_core.core.persistence.shared.db import get_engine, get_session
from ergon_core.core.persistence.shared.enums import SampleStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord
from ergon_core.core.application.runtime.models import MutationMeta
from ergon_core.core.application.runtime.graph_repository import RuntimeGraphRepository
from ergon_core.core.application.runtime.orchestration import PropagateTaskCompletionCommand
from ergon_core.core.application.runtime.sample_lifecycle import WorkflowService
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
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


def _cleanup_run(sample_id, defn_id) -> None:  # type: ignore[no-untyped-def]
    """Remove all rows created by a test, in FK-safe order."""
    with get_session() as session:
        for mut in session.exec(
            select(SampleGraphMutation).where(SampleGraphMutation.sample_id == sample_id)
        ).all():
            session.delete(mut)
        for edge in session.exec(
            select(SampleGraphEdge).where(SampleGraphEdge.sample_id == sample_id)
        ).all():
            session.delete(edge)
        for nd in session.exec(
            select(SampleGraphNode).where(SampleGraphNode.sample_id == sample_id)
        ).all():
            session.delete(nd)
        run_row = session.get(SampleRecord, sample_id)
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
    WorkflowService.propagate(). Expected to pass with current code.
    """
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        node_a = make_node(session, run.id, task_slug="task-a", status="running")
        sample_id = run.id
        defn_id = defn.id
        node_a_id = node_a.task_id
        session.commit()

    try:
        # Stamp RUNNING into the WAL so the WAL invariant check passes.
        graph_repo = RuntimeGraphRepository()
        with get_session() as session:
            await graph_repo.update_node_status(
                session,
                sample_id=sample_id,
                task_id=node_a_id,
                new_status=TaskExecutionStatus.RUNNING,
                meta=MutationMeta(actor="test:setup", reason="test setup: running"),
            )
            session.commit()

        # Propagate completion directly through the service.
        svc = WorkflowService()
        await svc.propagate(
            PropagateTaskCompletionCommand(
                sample_id=sample_id,
                definition_id=defn_id,
                task_id=node_a_id,
                execution_id=node_a_id,
            )
        )

        # --- Assertions ---
        with get_session() as session:
            status = get_node_status(session, node_a_id)
            assert status == TaskExecutionStatus.COMPLETED, (
                f"Expected node to be COMPLETED, got {status!r}"
            )
            assert_wal_has_status(session, node_a_id, "completed")

        # SampleRecord must not be FAILED after single-task happy-path completion.
        with get_session() as session:
            run_row = session.get(SampleRecord, sample_id)
            assert run_row is not None
            assert run_row.status != SampleStatus.FAILED, (
                f"SampleRecord should not be FAILED; got {run_row.status!r}"
            )

        with get_session() as session:
            assert_cross_cutting_invariants(session, sample_id)
    finally:
        _cleanup_run(sample_id, defn_id)
