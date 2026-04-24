"""Integration test — full manager restart scenario with diamond graph.

End-to-end scenario combining restart_task, downstream invalidation, and
re-activation in a single diamond-shaped managed-subtask graph:

    root (static)
      ├── task_a  (managed, COMPLETED)
      ├── task_b  (managed, COMPLETED)
      └── task_c  (managed, fan-in from task_a + task_b)

Phases:
  1. All tasks complete: task_c COMPLETED.
  2. Manager restarts task_a: task_a → PENDING, task_c → CANCELLED.
  3. task_a completes again (via propagate): task_c re-activates → PENDING.
  4. task_b is unaffected throughout.

This validates that restart + invalidation + re-activation compose correctly
across the full service stack.
"""

import pytest
from unittest.mock import AsyncMock, patch

from ergon_core.core.persistence.graph.status_conventions import CANCELLED, EDGE_PENDING
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.runtime.services.orchestration_dto import PropagateTaskCompletionCommand
from ergon_core.core.runtime.services.task_management_dto import RestartTaskCommand
from ergon_core.core.runtime.services.task_management_service import TaskManagementService
from ergon_core.core.runtime.services.task_propagation_service import TaskPropagationService

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
async def test_diamond_restart_invalidates_fanin_and_reactivates_on_recompletion() -> None:
    """Full diamond scenario: restart task_a, verify invalidation, then re-activation.

    Graph:
        task_a ──┐
                 ├──► task_c  (managed subtask, fan-in)
        task_b ──┘

    All start COMPLETED. Restarting task_a:
      - task_c becomes CANCELLED (stale output from previous run)
      - task_a becomes PENDING
      - task_b is unaffected

    After task_a completes again:
      - task_c re-activates to PENDING (all deps: task_a=COMPLETED, task_b=COMPLETED)
      - task_b remains COMPLETED throughout
    """
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        root = make_node(session, run.id, task_slug="root", status="completed")
        task_a = make_node(
            session,
            run.id,
            task_slug="task-a",
            status="completed",
            parent_node_id=root.id,
        )
        task_b = make_node(
            session,
            run.id,
            task_slug="task-b",
            status="completed",
            parent_node_id=root.id,
        )
        task_c = make_node(
            session,
            run.id,
            task_slug="task-c",
            status="completed",
            parent_node_id=root.id,
        )
        make_edge(
            session, run.id, source_node_id=task_a.id, target_node_id=task_c.id, status="satisfied"
        )
        make_edge(
            session, run.id, source_node_id=task_b.id, target_node_id=task_c.id, status="satisfied"
        )
        run_id = run.id
        defn_id = defn.id
        task_a_id = task_a.id
        task_b_id = task_b.id
        task_c_id = task_c.id
        session.commit()

    try:
        # ── Phase 1: verify initial state ────────────────────────────────
        with get_session() as session:
            assert get_node_status(session, task_a_id) == TaskExecutionStatus.COMPLETED
            assert get_node_status(session, task_b_id) == TaskExecutionStatus.COMPLETED
            assert get_node_status(session, task_c_id) == TaskExecutionStatus.COMPLETED

        # ── Phase 2: restart task_a ───────────────────────────────────────
        with patch(_TMS_INNGEST) as m1, patch(_EMITTER_INNGEST) as m2:
            m1.send = AsyncMock()
            m2.send = AsyncMock()
            svc = TaskManagementService()
            with get_session() as session:
                result = await svc.restart_task(
                    session,
                    RestartTaskCommand(run_id=run_id, node_id=task_a_id),
                )

        assert result.old_status == TaskExecutionStatus.COMPLETED
        assert task_c_id in result.invalidated_node_ids, (
            f"task_c must be in invalidated_node_ids; got {result.invalidated_node_ids!r}"
        )
        assert task_b_id not in result.invalidated_node_ids, (
            "task_b must NOT be invalidated — it is not downstream of task_a in this graph"
        )

        with get_session() as session:
            assert get_node_status(session, task_a_id) == TaskExecutionStatus.PENDING, (
                "task_a must be PENDING after restart"
            )
            assert get_node_status(session, task_c_id) == CANCELLED, (
                "task_c must be CANCELLED — its output was computed from the old task_a"
            )
            assert get_node_status(session, task_b_id) == TaskExecutionStatus.COMPLETED, (
                "task_b must remain COMPLETED — it is not downstream of task_a"
            )
            assert get_edge_status(session, run_id, task_a_id, task_c_id) == EDGE_PENDING, (
                "task_a→task_c edge must be reset to EDGE_PENDING"
            )
            assert get_edge_status(session, run_id, task_b_id, task_c_id) == EDGE_PENDING, (
                "task_b→task_c edge must be reset to EDGE_PENDING (task_c's incoming reset)"
            )

        # ── Phase 3: task_a completes again ──────────────────────────────
        # Use TaskPropagationService to simulate the normal completion path.
        # task_b is COMPLETED; task_a completing → all of task_c's deps are
        # COMPLETED → task_c re-activates from CANCELLED to PENDING.
        prop_svc = TaskPropagationService()
        await prop_svc.propagate(
            PropagateTaskCompletionCommand(
                run_id=run_id,
                definition_id=defn_id,
                task_id=task_a_id,
                execution_id=task_a_id,
                node_id=task_a_id,
            )
        )

        with get_session() as session:
            assert get_node_status(session, task_c_id) == TaskExecutionStatus.PENDING, (
                f"task_c must re-activate to PENDING once task_a (re)completes and "
                f"task_b is already COMPLETED; got {get_node_status(session, task_c_id)!r}"
            )
            assert get_node_status(session, task_b_id) == TaskExecutionStatus.COMPLETED, (
                "task_b must still be COMPLETED — unaffected throughout"
            )

    finally:
        cleanup_run(run_id, defn_id)
