"""Integration tests — CANCELLED managed-subtask re-activation after dep re-satisfies.

Propagation re-activates a CANCELLED node to PENDING when all its incoming
dependencies are COMPLETED — but only if the node is a *managed subtask*
(parent_node_id is not None). Static workflow nodes stay CANCELLED.

Covered here:
- CANCELLED managed subtask with all deps complete → re-activates to PENDING
- CANCELLED static node with all deps complete → stays CANCELLED
- Fan-in: CANCELLED managed subtask with two deps → re-activates only when
  BOTH deps complete, not when just one does
"""

import pytest

from sqlmodel import select

from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.graph.status_conventions import CANCELLED, EDGE_PENDING
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import RunRecord
from ergon_core.core.runtime.services.orchestration_dto import PropagateTaskCompletionCommand
from ergon_core.core.runtime.services.task_propagation_service import TaskPropagationService

from tests.integration.propagation._helpers import (
    get_node_status,
    make_edge,
    make_experiment_definition,
    make_node,
    make_run,
)
from tests.integration.restart._helpers import cleanup_run

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_cancelled_managed_subtask_reactivates_when_dep_completes() -> None:
    """CANCELLED managed subtask (parent_node_id set) re-activates when all deps complete.

    Simulates the state after restart_task ran and _invalidate_downstream
    cancelled node_b. When node_a completes again, propagation should
    re-activate node_b back to PENDING.
    """
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        root = make_node(session, run.id, task_slug="root", status="running")
        node_a = make_node(session, run.id, task_slug="task-a", status="completed")
        # node_b is a managed subtask — parent_node_id makes it eligible for re-activation
        node_b = make_node(
            session,
            run.id,
            task_slug="task-b",
            status=CANCELLED,
            parent_node_id=root.id,
        )
        # Edge is EDGE_PENDING: reset by restart_task / _invalidate_downstream
        make_edge(session, run.id, source_node_id=node_a.id, target_node_id=node_b.id)
        run_id = run.id
        defn_id = defn.id
        node_a_id = node_a.id
        node_b_id = node_b.id
        session.commit()

    try:
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

        with get_session() as session:
            b_status = get_node_status(session, node_b_id)
            assert b_status == TaskExecutionStatus.PENDING, (
                f"CANCELLED managed subtask must re-activate to PENDING when all deps complete; "
                f"got {b_status!r}"
            )
    finally:
        cleanup_run(run_id, defn_id)


@pytest.mark.asyncio
async def test_cancelled_static_node_does_not_reactivate() -> None:
    """CANCELLED static node (parent_node_id=None) does NOT re-activate when dep completes.

    Static workflow nodes have no manager to adapt them — they stay terminal.
    Only managed subtasks (with parent_node_id) are eligible for re-activation.
    """
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        node_a = make_node(session, run.id, task_slug="task-a", status="completed")
        # node_b is a static node — parent_node_id=None (default)
        node_b = make_node(session, run.id, task_slug="task-b-static", status=CANCELLED)
        make_edge(session, run.id, source_node_id=node_a.id, target_node_id=node_b.id)
        run_id = run.id
        defn_id = defn.id
        node_a_id = node_a.id
        node_b_id = node_b.id
        session.commit()

    try:
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

        with get_session() as session:
            b_status = get_node_status(session, node_b_id)
            assert b_status == CANCELLED, (
                f"Static CANCELLED node must remain CANCELLED; "
                f"only managed subtasks re-activate. Got {b_status!r}"
            )
    finally:
        cleanup_run(run_id, defn_id)


@pytest.mark.asyncio
async def test_fan_in_managed_subtask_reactivates_only_when_all_deps_complete() -> None:
    """Fan-in: managed subtask with two deps does not re-activate until both complete.

    A→C and B→C where C is CANCELLED managed subtask. Completing A alone
    must NOT re-activate C (B is still COMPLETED but needs to be checked).
    Actually we need to show the converse: completing A when B is already
    COMPLETED does re-activate C, and verify the all-deps check works.
    """
    with get_session() as session:
        defn = make_experiment_definition(session)
        run = make_run(session, defn.id)
        root = make_node(session, run.id, task_slug="root", status="running")
        node_a = make_node(session, run.id, task_slug="fan-a", status="completed")
        # B is not yet completed when we propagate A — verify C stays CANCELLED
        node_b = make_node(session, run.id, task_slug="fan-b", status="pending")
        node_c = make_node(
            session,
            run.id,
            task_slug="fan-c",
            status=CANCELLED,
            parent_node_id=root.id,
        )
        make_edge(session, run.id, source_node_id=node_a.id, target_node_id=node_c.id)
        make_edge(session, run.id, source_node_id=node_b.id, target_node_id=node_c.id)
        run_id = run.id
        defn_id = defn.id
        node_a_id = node_a.id
        node_b_id = node_b.id
        node_c_id = node_c.id
        session.commit()

    try:
        svc = TaskPropagationService()

        # Propagate A completing — B is still PENDING, so C must NOT re-activate
        await svc.propagate(
            PropagateTaskCompletionCommand(
                run_id=run_id,
                definition_id=defn_id,
                task_id=node_a_id,
                execution_id=node_a_id,
                node_id=node_a_id,
            )
        )

        with get_session() as session:
            c_status = get_node_status(session, node_c_id)
            assert c_status == CANCELLED, (
                f"C must remain CANCELLED while B is still PENDING; "
                f"all deps must be COMPLETED before re-activation. Got {c_status!r}"
            )

        # Now propagate B completing — both A and B are COMPLETED, so C re-activates
        await svc.propagate(
            PropagateTaskCompletionCommand(
                run_id=run_id,
                definition_id=defn_id,
                task_id=node_b_id,
                execution_id=node_b_id,
                node_id=node_b_id,
            )
        )

        with get_session() as session:
            c_status = get_node_status(session, node_c_id)
            assert c_status == TaskExecutionStatus.PENDING, (
                f"C must re-activate to PENDING once both A and B are COMPLETED; got {c_status!r}"
            )
    finally:
        cleanup_run(run_id, defn_id)
