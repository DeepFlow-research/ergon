"""Pure DAG state functions for task propagation.

All state is stored in the graph layer (RunGraphNode, RunGraphEdge,
RunGraphMutation). The graph mutation WAL is the single source of truth
for DAG execution state.

RunTaskStateEvent is no longer written or read by this module.
"""

from uuid import UUID

from ergon_core.api.json_types import JsonObject
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinitionTask,
    ExperimentDefinitionTaskDependency,
)
from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphNode
from ergon_core.core.persistence.graph.status_conventions import (
    BLOCKED,
    CANCELLED,
    EDGE_INVALIDATED,
    EDGE_SATISFIED,
    FAILED,
    RUNNING,
    TERMINAL_STATUSES,
)
from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_lookup import GraphNodeLookup
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from sqlmodel import Session, select

_PROPAGATION_META = MutationMeta(actor="system:propagation")


# ---------------------------------------------------------------------------
# Write helpers — all writes go through the graph repo
# ---------------------------------------------------------------------------


async def _update_task_status(
    session: Session,
    run_id: UUID,
    task_id: UUID,
    new_status: str,
    *,
    graph_repo: WorkflowGraphRepository,
    graph_lookup: GraphNodeLookup,
    event_metadata: JsonObject | None = None,
) -> None:
    node_id = graph_lookup.node_id(task_id)
    if node_id is None:
        return
    reason = None
    if event_metadata and "error" in event_metadata:
        reason = str(event_metadata["error"])
    await graph_repo.update_node_status(
        session,
        run_id=run_id,
        node_id=node_id,
        new_status=new_status,
        meta=MutationMeta(actor="system:propagation", reason=reason),
    )


async def mark_task_ready(
    session: Session,
    run_id: UUID,
    task_id: UUID,
    *,
    graph_repo: WorkflowGraphRepository,
    graph_lookup: GraphNodeLookup,
) -> None:
    await _update_task_status(
        session,
        run_id,
        task_id,
        TaskExecutionStatus.PENDING,
        graph_repo=graph_repo,
        graph_lookup=graph_lookup,
    )


async def mark_task_running(
    session: Session,
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID,
    *,
    graph_repo: WorkflowGraphRepository,
    graph_lookup: GraphNodeLookup,
) -> None:
    await _update_task_status(
        session,
        run_id,
        task_id,
        TaskExecutionStatus.RUNNING,
        graph_repo=graph_repo,
        graph_lookup=graph_lookup,
    )


async def mark_task_failed(
    session: Session,
    run_id: UUID,
    task_id: UUID,
    error: str,
    *,
    execution_id: UUID | None = None,
    graph_repo: WorkflowGraphRepository,
    graph_lookup: GraphNodeLookup,
) -> None:
    await _update_task_status(
        session,
        run_id,
        task_id,
        TaskExecutionStatus.FAILED,
        graph_repo=graph_repo,
        graph_lookup=graph_lookup,
        event_metadata={"error": error},
    )


# ---------------------------------------------------------------------------
# Read helpers — all reads go through RunGraphNode
# ---------------------------------------------------------------------------


async def get_initial_ready_tasks(
    session: Session,
    run_id: UUID,
    definition_id: UUID,
    *,
    graph_repo: WorkflowGraphRepository,
    graph_lookup: GraphNodeLookup,
) -> list[UUID]:
    """Return task IDs that have zero dependencies (root tasks)."""
    all_tasks_stmt = select(ExperimentDefinitionTask.id).where(
        ExperimentDefinitionTask.experiment_definition_id == definition_id,
    )
    all_task_ids = set(session.exec(all_tasks_stmt).all())

    tasks_with_deps_stmt = select(ExperimentDefinitionTaskDependency.task_id).where(
        ExperimentDefinitionTaskDependency.experiment_definition_id == definition_id,
    )
    tasks_with_deps = set(session.exec(tasks_with_deps_stmt).all())

    ready_ids = list(all_task_ids - tasks_with_deps)

    for tid in ready_ids:
        await mark_task_ready(
            session,
            run_id,
            tid,
            graph_repo=graph_repo,
            graph_lookup=graph_lookup,
        )

    session.commit()
    return ready_ids


# ---------------------------------------------------------------------------
# Graph-native write helpers (no GraphNodeLookup)
# ---------------------------------------------------------------------------


async def mark_task_failed_by_node(
    session: Session,
    run_id: UUID,
    node_id: UUID,
    error: str,
    *,
    execution_id: UUID | None = None,
    graph_repo: WorkflowGraphRepository,
) -> None:
    await graph_repo.update_node_status(
        session,
        run_id=run_id,
        node_id=node_id,
        new_status=TaskExecutionStatus.FAILED,
        meta=MutationMeta(
            actor="system:propagation",
            reason=error,
        ),
    )


# ---------------------------------------------------------------------------
# Graph-native propagation (no GraphNodeLookup, walks RunGraphEdge)
# ---------------------------------------------------------------------------


async def _block_successors_bfs(
    session: Session,
    run_id: UUID,
    seed_node_ids: set[UUID],
    *,
    failed_node_id: UUID,
    terminal_status: str,
    graph_repo: WorkflowGraphRepository,
) -> None:
    """BFS: propagate BLOCKED through the entire reachable subgraph.

    Starts from seed_node_ids (direct successors of the failed node). When a
    node is BLOCKED, its own outgoing edges are INVALIDATED and its successors
    enqueued so BLOCKED propagates transitively (e.g. A→B→C, A fails → both
    B and C become BLOCKED in one synchronous pass).

    RUNNING and terminal nodes are skipped.
    """
    queue = list(seed_node_ids)
    while queue:
        target_id = queue.pop()
        target_node = session.get(RunGraphNode, target_id)
        if target_node is None:
            continue
        if target_node.status == RUNNING:
            continue
        if target_node.status in TERMINAL_STATUSES:
            continue

        applied = await graph_repo.update_node_status(
            session,
            run_id=run_id,
            node_id=target_id,
            new_status=BLOCKED,
            meta=MutationMeta(
                actor="system:propagation",
                reason=f"dependency {failed_node_id} {terminal_status}",
            ),
            only_if_not_terminal=True,
        )

        if applied:
            target_outgoing = list(
                session.exec(
                    select(RunGraphEdge).where(
                        RunGraphEdge.run_id == run_id,
                        RunGraphEdge.source_node_id == target_id,
                    )
                ).all()
            )
            for edge in target_outgoing:
                await graph_repo.update_edge_status(
                    session,
                    run_id=run_id,
                    edge_id=edge.id,
                    new_status=EDGE_INVALIDATED,
                    meta=_PROPAGATION_META,
                )
                queue.append(edge.target_node_id)


async def on_task_completed_or_failed(
    session: Session,
    run_id: UUID,
    node_id: UUID,
    terminal_status: str,
    *,
    graph_repo: WorkflowGraphRepository,
) -> tuple[list[UUID], list[UUID]]:
    """Handle a node reaching COMPLETED, FAILED, or CANCELLED.

    Returns (newly_ready_node_ids, invalidated_target_node_ids).

    - COMPLETED: outgoing edges become SATISFIED; targets with all deps
      satisfied become READY.
    - FAILED / CANCELLED: outgoing edges become INVALIDATED.  For static
      workflow nodes (parent_node_id is None), targets are auto-cancelled
      and reported as invalidated.  For dynamic subtasks (parent_node_id
      set), targets stay PENDING so the manager can adapt — the edge is
      invalidated but the node is left for the manager to retry, cancel,
      or re-plan via the subtask lifecycle tools.

    Walks RunGraphEdge so it works for both static and dynamic tasks.

    Precondition: the caller must ensure node_id is already in terminal_status
    before calling this function. The node's own status is NOT written here —
    only edge statuses and downstream candidate statuses are updated.
    """
    is_success = terminal_status == TaskExecutionStatus.COMPLETED

    outgoing = list(
        session.exec(
            select(RunGraphEdge).where(
                RunGraphEdge.run_id == run_id,
                RunGraphEdge.source_node_id == node_id,
            )
        ).all()
    )

    edge_status = EDGE_SATISFIED if is_success else EDGE_INVALIDATED
    for edge in outgoing:
        await graph_repo.update_edge_status(
            session,
            run_id=run_id,
            edge_id=edge.id,
            new_status=edge_status,
            meta=_PROPAGATION_META,
        )

    candidate_node_ids = {e.target_node_id for e in outgoing}

    newly_ready: list[UUID] = []
    invalidated: list[UUID] = []

    if not is_success:
        await _block_successors_bfs(
            session,
            run_id=run_id,
            seed_node_ids=candidate_node_ids,
            failed_node_id=node_id,
            terminal_status=terminal_status,
            graph_repo=graph_repo,
        )
        session.commit()
        return newly_ready, invalidated

    # SUCCESS PATH: source completed — check if candidates can become READY.
    for candidate_id in candidate_node_ids:
        candidate_node = session.get(RunGraphNode, candidate_id)
        if candidate_node is None:
            continue
        if candidate_node.status in TERMINAL_STATUSES and candidate_node.status != CANCELLED:
            continue

        # Eligibility:
        #   - PENDING (first activation): normal case.
        #   - CANCELLED managed subtask (parent_node_id is not None):
        #     re-activation after the manager or an upstream restart
        #     invalidated it. Policy: any CANCELLED managed subtask
        #     re-activates when all deps re-satisfy; if the manager
        #     explicitly cancelled and doesn't want it re-activated it
        #     can re-cancel. Keeps propagation logic simple and avoids
        #     needing a cancel_cause column on the node.
        #   - CANCELLED static workflow node (parent_node_id is None):
        #     NOT re-activated — no supervisor to adapt, and the static
        #     workflow expects terminal nodes to stay terminal.
        #
        # Everything else (COMPLETED, FAILED, RUNNING, BLOCKED) is skipped.
        status = candidate_node.status
        is_managed_subtask = candidate_node.parent_node_id is not None
        is_pending = status == TaskExecutionStatus.PENDING
        is_reactivatable_cancelled = status == CANCELLED and is_managed_subtask

        if not (is_pending or is_reactivatable_cancelled):
            continue

        incoming = list(
            session.exec(
                select(RunGraphEdge).where(
                    RunGraphEdge.run_id == run_id,
                    RunGraphEdge.target_node_id == candidate_id,
                )
            ).all()
        )

        source_nodes = [session.get(RunGraphNode, e.source_node_id) for e in incoming]
        if all(n is not None and n.status == TaskExecutionStatus.COMPLETED for n in source_nodes):
            reason = (
                f"all dependencies satisfied after {node_id}"
                if is_pending
                else f"re-activating cancelled subtask after {node_id}"
            )
            await graph_repo.update_node_status(
                session,
                run_id=run_id,
                node_id=candidate_id,
                new_status=TaskExecutionStatus.PENDING,
                meta=MutationMeta(
                    actor="system:propagation",
                    reason=reason,
                ),
                # Must be False for the CANCELLED -> PENDING transition;
                # CANCELLED is terminal and only_if_not_terminal=True
                # would block the re-activation write.
                only_if_not_terminal=False,
            )
            newly_ready.append(candidate_id)

    session.commit()
    return newly_ready, invalidated


# ---------------------------------------------------------------------------
# Graph-native terminal-state checks (no definition_id)
# ---------------------------------------------------------------------------


def is_workflow_complete_v2(session: Session, run_id: UUID) -> bool:
    """Every node terminal; zero FAILED. CANCELLED is neutral."""
    statuses = list(
        session.exec(select(RunGraphNode.status).where(RunGraphNode.run_id == run_id)).all()
    )
    if not statuses:
        return True
    return all(s in TERMINAL_STATUSES for s in statuses) and not any(s == FAILED for s in statuses)


_SETTLED_STATUSES = TERMINAL_STATUSES | frozenset({BLOCKED})


def is_workflow_failed_v2(session: Session, run_id: UUID) -> bool:
    """All nodes settled (terminal or BLOCKED) AND at least one FAILED.

    BLOCKED nodes represent predecessor-failed state awaiting operator action.
    Once all remaining work is settled — either terminal or BLOCKED with no
    PENDING/RUNNING tasks remaining — the run cannot make further autonomous
    progress. Treat this as a workflow failure so the RunRecord transitions to
    FAILED and criterion evaluation fires.

    BLOCKED nodes are preserved (not CANCELLED) so the operator can examine
    them and use operator_unblock / restart_node to resume if desired.
    """
    statuses = list(
        session.exec(select(RunGraphNode.status).where(RunGraphNode.run_id == run_id)).all()
    )
    if not statuses:
        return False
    all_settled = all(s in _SETTLED_STATUSES for s in statuses)
    return all_settled and any(s == FAILED for s in statuses)
