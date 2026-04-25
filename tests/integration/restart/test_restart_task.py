"""Integration tests — TaskManagementService.restart_task and refine_task.

Covers:
- Restart COMPLETED / FAILED / CANCELLED → PENDING with WAL entry
- Restart PENDING / RUNNING → TaskNotTerminalError
- Outgoing edges reset to EDGE_PENDING after restart
- refine_task: RUNNING raises TaskRunningError; non-running (COMPLETED) accepted
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
from ergon_core.core.runtime.errors.delegation_errors import TaskNotTerminalError, TaskRunningError
from ergon_core.core.runtime.services.task_management_dto import (
    RefineTaskCommand,
    RestartTaskCommand,
)
from ergon_core.core.runtime.services.task_management_service import TaskManagementService

from tests.integration.propagation._helpers import (
    assert_wal_has_status,
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
async def test_restart_completed_node_becomes_pending_and_resets_edge() -> None:
    """Restarting a COMPLETED node transitions it to PENDING and resets outgoing edges to PENDING.

    Also verifies the WAL has a PENDING entry for the restarted node and
    that the return value reports the correct old_status.
    """
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        node_a = make_node(session, run.id, task_slug="task-a", status="completed")
        node_b = make_node(session, run.id, task_slug="task-b", status="pending")
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

        assert result.old_status == TaskExecutionStatus.COMPLETED
        assert result.node_id == node_a_id

        with get_session() as session:
            assert get_node_status(session, node_a_id) == TaskExecutionStatus.PENDING, (
                "node_a must be PENDING after restart"
            )
            assert_wal_has_status(session, node_a_id, "pending")
            edge_st = get_edge_status(session, run_id, node_a_id, node_b_id)
            assert edge_st == EDGE_PENDING, (
                f"Edge A→B must be reset to EDGE_PENDING after restart; got {edge_st!r}"
            )
    finally:
        cleanup_run(run_id, defn_id)


@pytest.mark.asyncio
async def test_restart_failed_node_becomes_pending() -> None:
    """Restarting a FAILED node transitions it to PENDING."""
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        node_a = make_node(session, run.id, task_slug="failed-task", status="failed")
        run_id = run.id
        defn_id = defn.id
        node_a_id = node_a.id
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

        assert result.old_status == TaskExecutionStatus.FAILED
        with get_session() as session:
            assert get_node_status(session, node_a_id) == TaskExecutionStatus.PENDING
    finally:
        cleanup_run(run_id, defn_id)


@pytest.mark.asyncio
async def test_restart_cancelled_node_becomes_pending() -> None:
    """Restarting a CANCELLED node transitions it to PENDING."""
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        node_a = make_node(session, run.id, task_slug="cancelled-task", status=CANCELLED)
        run_id = run.id
        defn_id = defn.id
        node_a_id = node_a.id
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

        assert result.old_status == CANCELLED
        with get_session() as session:
            assert get_node_status(session, node_a_id) == TaskExecutionStatus.PENDING
    finally:
        cleanup_run(run_id, defn_id)


@pytest.mark.asyncio
async def test_restart_pending_node_raises() -> None:
    """Restarting a PENDING node raises TaskNotTerminalError."""
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        node_a = make_node(session, run.id, task_slug="pending-task", status="pending")
        run_id = run.id
        defn_id = defn.id
        node_a_id = node_a.id
        session.commit()

    try:
        with patch(_TMS_INNGEST) as m1, patch(_EMITTER_INNGEST) as m2:
            m1.send = AsyncMock()
            m2.send = AsyncMock()
            svc = TaskManagementService()
            with get_session() as session:
                with pytest.raises(TaskNotTerminalError):
                    await svc.restart_task(
                        session,
                        RestartTaskCommand(run_id=run_id, node_id=node_a_id),
                    )
    finally:
        cleanup_run(run_id, defn_id)


@pytest.mark.asyncio
async def test_restart_running_node_raises() -> None:
    """Restarting a RUNNING node raises TaskNotTerminalError (RUNNING is non-terminal)."""
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        node_a = make_node(session, run.id, task_slug="running-task", status="running")
        run_id = run.id
        defn_id = defn.id
        node_a_id = node_a.id
        session.commit()

    try:
        with patch(_TMS_INNGEST) as m1, patch(_EMITTER_INNGEST) as m2:
            m1.send = AsyncMock()
            m2.send = AsyncMock()
            svc = TaskManagementService()
            with get_session() as session:
                with pytest.raises(TaskNotTerminalError):
                    await svc.restart_task(
                        session,
                        RestartTaskCommand(run_id=run_id, node_id=node_a_id),
                    )
    finally:
        cleanup_run(run_id, defn_id)


@pytest.mark.asyncio
async def test_refine_task_non_pending_node_succeeds() -> None:
    """refine_task accepts a COMPLETED node — widened beyond PENDING for restart flow."""
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        node_a = make_node(session, run.id, task_slug="refine-completed", status="completed")
        run_id = run.id
        defn_id = defn.id
        node_a_id = node_a.id
        session.commit()

    try:
        with patch(_TMS_INNGEST) as m1, patch(_EMITTER_INNGEST) as m2:
            m1.send = AsyncMock()
            m2.send = AsyncMock()
            svc = TaskManagementService()
            with get_session() as session:
                result = await svc.refine_task(
                    session,
                    RefineTaskCommand(
                        run_id=run_id,
                        node_id=node_a_id,
                        new_description="Updated after restart",
                    ),
                )

        assert result.new_description == "Updated after restart"
    finally:
        cleanup_run(run_id, defn_id)


@pytest.mark.asyncio
async def test_refine_task_running_node_raises() -> None:
    """refine_task raises TaskRunningError for a RUNNING node."""
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        node_a = make_node(session, run.id, task_slug="refine-running", status="running")
        run_id = run.id
        defn_id = defn.id
        node_a_id = node_a.id
        session.commit()

    try:
        with patch(_TMS_INNGEST) as m1, patch(_EMITTER_INNGEST) as m2:
            m1.send = AsyncMock()
            m2.send = AsyncMock()
            svc = TaskManagementService()
            with get_session() as session:
                with pytest.raises(TaskRunningError):
                    await svc.refine_task(
                        session,
                        RefineTaskCommand(
                            run_id=run_id,
                            node_id=node_a_id,
                            new_description="Should not update",
                        ),
                    )
    finally:
        cleanup_run(run_id, defn_id)
