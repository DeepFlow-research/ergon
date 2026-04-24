"""Integration tests — _invalidate_downstream cascade behavior.

Covers:
- COMPLETED direct successor is cancelled and recursed into
- Non-terminal (PENDING) direct successor is cancelled but NOT recursed
- FAILED / CANCELLED successors are skipped entirely
- Deep cascade: A→B→C all COMPLETED — restart A cancels both B and C
"""

import pytest
from unittest.mock import AsyncMock, patch

from sqlmodel import select

from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.graph.status_conventions import (
    CANCELLED,
    EDGE_PENDING,
    EDGE_SATISFIED,
)
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import RunRecord
from ergon_core.core.runtime.services.task_management_dto import RestartTaskCommand
from ergon_core.core.runtime.services.task_management_service import TaskManagementService

from tests.integration.propagation._helpers import (
    get_node_status,
    make_edge,
    make_experiment_definition,
    make_node,
    make_run,
)
from tests.integration.restart._helpers import cleanup_run, get_edge_status

pytestmark = pytest.mark.integration

_TMS_INNGEST = "ergon_core.core.runtime.services.task_management_service.inngest_client"
_EMITTER_INNGEST = "ergon_core.core.dashboard.emitter.inngest_client"


@pytest.mark.asyncio
async def test_completed_successor_is_cancelled_by_invalidation() -> None:
    """A→B. B is COMPLETED. Restarting A cancels B (stale output).

    B is a COMPLETED downstream node whose output was computed from A's
    previous run. When A is restarted, B's output is stale, so it must
    be cancelled by _invalidate_downstream.
    """
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        node_a = make_node(session, run.id, task_slug="task-a", status="completed")
        node_b = make_node(session, run.id, task_slug="task-b", status="completed")
        make_edge(
            session,
            run.id,
            source_node_id=node_a.id,
            target_node_id=node_b.id,
            status=EDGE_SATISFIED,
        )
        run_id = run.id
        defn_id = defn.id
        node_a_id = node_a.id
        node_b_id = node_b.id
        session.commit()

    try:
        with patch(_TMS_INNGEST) as m1, patch(_EMITTER_INNGEST) as m2:
            m1.send = AsyncMock()
            m2.send = AsyncMock()
            svc = TaskManagementService()
            with get_session() as session:
                result = await svc.restart_task(
                    session,
                    RestartTaskCommand(run_id=run_id, node_id=node_a_id),
                )

        assert node_b_id in result.invalidated_node_ids, (
            f"Expected B in invalidated_node_ids; got {result.invalidated_node_ids!r}"
        )

        with get_session() as session:
            assert get_node_status(session, node_a_id) == TaskExecutionStatus.PENDING
            assert get_node_status(session, node_b_id) == CANCELLED, (
                "B must be CANCELLED — its output is stale after A was restarted"
            )
            assert get_edge_status(session, run_id, node_a_id, node_b_id) == EDGE_PENDING, (
                "Edge A→B must be reset to EDGE_PENDING so re-run of A can re-satisfy it"
            )
    finally:
        cleanup_run(run_id, defn_id)


@pytest.mark.asyncio
async def test_pending_successor_is_cancelled_but_cascade_stops_there() -> None:
    """A→B→C. B is PENDING, C is COMPLETED. Restarting A cancels B but NOT C.

    Non-terminal nodes (PENDING/RUNNING) have no stale output, so recursion
    stops. C is not invalidated because B never completed.
    """
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        node_a = make_node(session, run.id, task_slug="task-a", status="completed")
        node_b = make_node(session, run.id, task_slug="task-b", status="pending")
        node_c = make_node(session, run.id, task_slug="task-c", status="completed")
        make_edge(
            session,
            run.id,
            source_node_id=node_a.id,
            target_node_id=node_b.id,
            status=EDGE_SATISFIED,
        )
        make_edge(
            session,
            run.id,
            source_node_id=node_b.id,
            target_node_id=node_c.id,
            status=EDGE_SATISFIED,
        )
        run_id = run.id
        defn_id = defn.id
        node_a_id = node_a.id
        node_b_id = node_b.id
        node_c_id = node_c.id
        session.commit()

    try:
        with patch(_TMS_INNGEST) as m1, patch(_EMITTER_INNGEST) as m2:
            m1.send = AsyncMock()
            m2.send = AsyncMock()
            svc = TaskManagementService()
            with get_session() as session:
                result = await svc.restart_task(
                    session,
                    RestartTaskCommand(run_id=run_id, node_id=node_a_id),
                )

        assert node_b_id in result.invalidated_node_ids, "B must be invalidated"
        assert node_c_id not in result.invalidated_node_ids, (
            "C must NOT be invalidated — cascade stops at non-terminal B"
        )

        with get_session() as session:
            assert get_node_status(session, node_b_id) == CANCELLED, (
                "B must be CANCELLED — it had stale input"
            )
            assert get_node_status(session, node_c_id) == TaskExecutionStatus.COMPLETED, (
                "C must remain COMPLETED — cascade does not recurse through non-terminal B"
            )
    finally:
        cleanup_run(run_id, defn_id)


@pytest.mark.asyncio
async def test_failed_and_cancelled_successors_are_skipped() -> None:
    """A→B, A→C. B is FAILED, C is CANCELLED. Restarting A touches neither.

    FAILED and CANCELLED successors are already terminal with no stale
    output. _invalidate_downstream skips them; only A's outgoing edges
    are reset to EDGE_PENDING.
    """
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        node_a = make_node(session, run.id, task_slug="task-a", status="completed")
        node_b = make_node(session, run.id, task_slug="task-b-failed", status="failed")
        node_c = make_node(session, run.id, task_slug="task-c-cancelled", status=CANCELLED)
        make_edge(
            session,
            run.id,
            source_node_id=node_a.id,
            target_node_id=node_b.id,
            status=EDGE_SATISFIED,
        )
        make_edge(
            session,
            run.id,
            source_node_id=node_a.id,
            target_node_id=node_c.id,
            status=EDGE_SATISFIED,
        )
        run_id = run.id
        defn_id = defn.id
        node_a_id = node_a.id
        node_b_id = node_b.id
        node_c_id = node_c.id
        session.commit()

    try:
        with patch(_TMS_INNGEST) as m1, patch(_EMITTER_INNGEST) as m2:
            m1.send = AsyncMock()
            m2.send = AsyncMock()
            svc = TaskManagementService()
            with get_session() as session:
                result = await svc.restart_task(
                    session,
                    RestartTaskCommand(run_id=run_id, node_id=node_a_id),
                )

        assert result.invalidated_node_ids == [], (
            f"No nodes should be invalidated when all successors are FAILED/CANCELLED; "
            f"got {result.invalidated_node_ids!r}"
        )

        with get_session() as session:
            assert get_node_status(session, node_b_id) == TaskExecutionStatus.FAILED, (
                "FAILED successor must not be overwritten"
            )
            assert get_node_status(session, node_c_id) == CANCELLED, (
                "CANCELLED successor must not be overwritten"
            )
            assert get_edge_status(session, run_id, node_a_id, node_b_id) == EDGE_PENDING, (
                "A→B edge must be reset to EDGE_PENDING so B can be retried later"
            )
            assert get_edge_status(session, run_id, node_a_id, node_c_id) == EDGE_PENDING, (
                "A→C edge must be reset to EDGE_PENDING so C can be retried later"
            )
    finally:
        cleanup_run(run_id, defn_id)


@pytest.mark.asyncio
async def test_cascade_invalidation_recurses_through_completed_chain() -> None:
    """A→B→C, all COMPLETED. Restarting A cancels both B and C.

    _invalidate_downstream recurses through COMPLETED nodes, so the full
    downstream chain is invalidated, not just the immediate successor.
    """
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        node_a = make_node(session, run.id, task_slug="chain-a", status="completed")
        node_b = make_node(session, run.id, task_slug="chain-b", status="completed")
        node_c = make_node(session, run.id, task_slug="chain-c", status="completed")
        make_edge(
            session,
            run.id,
            source_node_id=node_a.id,
            target_node_id=node_b.id,
            status=EDGE_SATISFIED,
        )
        make_edge(
            session,
            run.id,
            source_node_id=node_b.id,
            target_node_id=node_c.id,
            status=EDGE_SATISFIED,
        )
        run_id = run.id
        defn_id = defn.id
        node_a_id = node_a.id
        node_b_id = node_b.id
        node_c_id = node_c.id
        session.commit()

    try:
        with patch(_TMS_INNGEST) as m1, patch(_EMITTER_INNGEST) as m2:
            m1.send = AsyncMock()
            m2.send = AsyncMock()
            svc = TaskManagementService()
            with get_session() as session:
                result = await svc.restart_task(
                    session,
                    RestartTaskCommand(run_id=run_id, node_id=node_a_id),
                )

        assert set(result.invalidated_node_ids) == {node_b_id, node_c_id}, (
            f"Both B and C must be invalidated in a full COMPLETED chain; "
            f"got {result.invalidated_node_ids!r}"
        )

        with get_session() as session:
            assert get_node_status(session, node_a_id) == TaskExecutionStatus.PENDING
            assert get_node_status(session, node_b_id) == CANCELLED, (
                "B must be CANCELLED (direct COMPLETED successor)"
            )
            assert get_node_status(session, node_c_id) == CANCELLED, (
                "C must be CANCELLED (COMPLETED via recursion through B)"
            )
            assert get_edge_status(session, run_id, node_a_id, node_b_id) == EDGE_PENDING
            assert get_edge_status(session, run_id, node_b_id, node_c_id) == EDGE_PENDING, (
                "B→C edge must also be reset to EDGE_PENDING by the cascade"
            )
    finally:
        cleanup_run(run_id, defn_id)
