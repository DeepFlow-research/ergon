"""Workflow propagation service helpers.

All state is stored in the graph layer (RunGraphNode, RunGraphEdge,
RunGraphMutation). The graph mutation WAL is the single source of truth
for DAG execution state.
"""

from uuid import UUID

from ergon_core.core.shared.json_types import JsonObject
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinitionTask,
    ExperimentDefinitionTaskDependency,
)
from ergon_core.core.persistence.graph import status_conventions as graph_status
from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphNode
from ergon_core.core.application.graph.models import MutationMeta
from ergon_core.core.application.graph.lookup import GraphNodeLookup
from ergon_core.core.application.graph.repository import WorkflowGraphRepository
from sqlmodel import Session, select

_PROPAGATION_META = MutationMeta(actor="system:propagation")


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
        graph_status.PENDING,
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
        graph_status.RUNNING,
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
        graph_status.FAILED,
        graph_repo=graph_repo,
        graph_lookup=graph_lookup,
        event_metadata={"error": error},
    )


async def get_initial_ready_tasks(
    session: Session,
    run_id: UUID,
    definition_id: UUID,
    *,
    graph_repo: WorkflowGraphRepository,
    graph_lookup: GraphNodeLookup,
) -> list[UUID]:
    """Return task IDs that have zero dependencies."""
    all_tasks_stmt = select(ExperimentDefinitionTask.id).where(
        ExperimentDefinitionTask.experiment_definition_id == definition_id,
    )
    all_task_ids = set(session.exec(all_tasks_stmt).all())

    tasks_with_deps_stmt = select(ExperimentDefinitionTaskDependency.task_id).where(
        ExperimentDefinitionTaskDependency.experiment_definition_id == definition_id,
    )
    tasks_with_deps = set(session.exec(tasks_with_deps_stmt).all())

    ready_ids = list(all_task_ids - tasks_with_deps)

    for task_id in ready_ids:
        await mark_task_ready(
            session,
            run_id,
            task_id,
            graph_repo=graph_repo,
            graph_lookup=graph_lookup,
        )

    session.commit()
    return ready_ids


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
        new_status=graph_status.FAILED,
        meta=MutationMeta(
            actor="system:propagation",
            reason=error,
        ),
    )


async def _block_successors_bfs(
    session: Session,
    run_id: UUID,
    seed_node_ids: set[UUID],
    *,
    failed_node_id: UUID,
    terminal_status: str,
    graph_repo: WorkflowGraphRepository,
) -> None:
    """Propagate BLOCKED through the reachable downstream graph."""
    queue = list(seed_node_ids)
    while queue:
        target_id = queue.pop()
        target_node = session.get(RunGraphNode, target_id)
        if target_node is None:
            continue
        if target_node.status == graph_status.RUNNING:
            continue
        if target_node.status in graph_status.TERMINAL_STATUSES:
            continue

        applied = await graph_repo.update_node_status(
            session,
            run_id=run_id,
            node_id=target_id,
            new_status=graph_status.BLOCKED,
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
                        RunGraphEdge.source_task_id == target_id,
                    )
                ).all()
            )
            for edge in target_outgoing:
                await graph_repo.update_edge_status(
                    session,
                    run_id=run_id,
                    edge_id=edge.id,
                    new_status=graph_status.EDGE_INVALIDATED,
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
) -> list[UUID]:
    """Handle a node reaching COMPLETED, FAILED, or CANCELLED."""
    is_success = terminal_status == graph_status.COMPLETED

    outgoing = list(
        session.exec(
            select(RunGraphEdge).where(
                RunGraphEdge.run_id == run_id,
                RunGraphEdge.source_task_id == node_id,
            )
        ).all()
    )

    edge_status = graph_status.EDGE_SATISFIED if is_success else graph_status.EDGE_INVALIDATED
    for edge in outgoing:
        await graph_repo.update_edge_status(
            session,
            run_id=run_id,
            edge_id=edge.id,
            new_status=edge_status,
            meta=_PROPAGATION_META,
        )

    candidate_node_ids = {edge.target_node_id for edge in outgoing}
    newly_ready: list[UUID] = []

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
        return newly_ready

    for candidate_id in candidate_node_ids:
        candidate_node = session.get(RunGraphNode, candidate_id)
        if candidate_node is None:
            continue
        if (
            candidate_node.status in graph_status.TERMINAL_STATUSES
            and candidate_node.status != graph_status.CANCELLED
        ):
            continue

        status = candidate_node.status
        is_managed_subtask = candidate_node.parent_task_id is not None
        is_pending = status == graph_status.PENDING
        is_reactivatable_cancelled = status == graph_status.CANCELLED and is_managed_subtask

        if not (is_pending or is_reactivatable_cancelled):
            continue

        incoming = list(
            session.exec(
                select(RunGraphEdge).where(
                    RunGraphEdge.run_id == run_id,
                    RunGraphEdge.target_task_id == candidate_id,
                )
            ).all()
        )

        source_nodes = [session.get(RunGraphNode, edge.source_node_id) for edge in incoming]
        if all(node is not None and node.status == graph_status.COMPLETED for node in source_nodes):
            reason = (
                f"all dependencies satisfied after {node_id}"
                if is_pending
                else f"re-activating cancelled subtask after {node_id}"
            )
            await graph_repo.update_node_status(
                session,
                run_id=run_id,
                node_id=candidate_id,
                new_status=graph_status.PENDING,
                meta=MutationMeta(
                    actor="system:propagation",
                    reason=reason,
                ),
                only_if_not_terminal=False,
            )
            newly_ready.append(candidate_id)

    session.commit()
    return newly_ready


def is_workflow_complete_v2(session: Session, run_id: UUID) -> bool:
    """Every node terminal; zero FAILED. CANCELLED is neutral."""
    statuses = list(
        session.exec(select(RunGraphNode.status).where(RunGraphNode.run_id == run_id)).all()
    )
    if not statuses:
        return True
    return all(status in graph_status.TERMINAL_STATUSES for status in statuses) and not any(
        status == graph_status.FAILED for status in statuses
    )


_SETTLED_STATUSES = graph_status.TERMINAL_STATUSES | frozenset({graph_status.BLOCKED})


def is_workflow_failed_v2(session: Session, run_id: UUID) -> bool:
    """All nodes settled and at least one FAILED."""
    statuses = list(
        session.exec(select(RunGraphNode.status).where(RunGraphNode.run_id == run_id)).all()
    )
    if not statuses:
        return False
    all_settled = all(status in _SETTLED_STATUSES for status in statuses)
    return all_settled and any(status == graph_status.FAILED for status in statuses)
