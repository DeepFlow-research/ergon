"""Test 8 — restart semantics.

Covers restart_task and the BLOCKED-node constraint that prevents restart_task
from accepting a BLOCKED node (BLOCKED ∉ TERMINAL_STATUSES).

The full restart/invalidation/reactivation suite lives in
tests/integration/restart/; these tests anchor the propagation-level
perspective on the same feature.
"""

from unittest.mock import AsyncMock, patch

import pytest
from ergon_core.core.application.runtime.status import BLOCKED
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.application.runtime.task_errors import TaskNotTerminalError
from ergon_core.core.application.runtime.task_models import RestartTaskCommand
from ergon_core.core.application.runtime.task_management import TaskManagementService

from tests.integration.propagation._helpers import (
    delete_typed_sample_wal,
    get_node_status,
    make_edge,
    make_node,
    make_run,
)
from tests.integration.restart._helpers import cleanup_run

pytestmark = pytest.mark.integration

_TMS_INNGEST = "ergon_core.core.application.runtime.task_management.inngest_client"
_EMITTER_INNGEST = "ergon_core.core.infrastructure.dashboard.emitter.inngest_client"


@pytest.mark.asyncio
async def test_8_blocked_node_cannot_be_restarted() -> None:
    """restart_task rejects BLOCKED nodes — BLOCKED ∉ TERMINAL_STATUSES.

    BLOCKED represents a node whose predecessor failed; the operator must
    restart the failed predecessor (which re-satisfies the edge) rather than
    directly restarting the BLOCKED downstream node.  restart_task enforces
    this by requiring terminal status (COMPLETED / FAILED / CANCELLED) and
    raising TaskNotTerminalError for anything else.
    """
    with get_session() as session:
        run = make_run(session)
        node_a = make_node(session, run.id, task_slug="task-a-failed", status="failed")
        node_b = make_node(session, run.id, task_slug="task-b-blocked", status=BLOCKED)
        make_edge(session, run.id, source_task_id=node_a.task_id, target_task_id=node_b.task_id)
        sample_id = run.id
        node_b_id = node_b.task_id
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
                        RestartTaskCommand(sample_id=sample_id, task_id=node_b_id),
                    )
    finally:
        cleanup_run(sample_id)


@pytest.mark.asyncio
async def test_8b_restart_failed_node_re_enters_pending() -> None:
    """A FAILED node can be restarted via restart_task, transitioning to PENDING.

    Operator calls restart_task on a FAILED node. The node becomes PENDING
    so it can be re-scheduled for execution.
    """
    with get_session() as session:
        run = make_run(session)
        node_a = make_node(session, run.id, task_slug="task-a-to-restart", status="failed")
        sample_id = run.id
        node_a_id = node_a.task_id
        session.commit()

    try:
        with patch(_TMS_INNGEST) as m1, patch(_EMITTER_INNGEST) as m2:
            m1.send = AsyncMock()
            m2.send = AsyncMock()
            svc = TaskManagementService()
            with get_session() as session:
                result = await svc.restart_task(
                    session,
                    RestartTaskCommand(sample_id=sample_id, task_id=node_a_id),
                )

        assert result.old_status == TaskExecutionStatus.FAILED
        with get_session() as session:
            assert get_node_status(session, node_a_id) == TaskExecutionStatus.PENDING, (
                f"Expected A to be PENDING after restart_task; got {get_node_status(session, node_a_id)!r}"
            )

    finally:
        cleanup_run(sample_id)
