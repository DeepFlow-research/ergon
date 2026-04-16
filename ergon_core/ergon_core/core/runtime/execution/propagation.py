"""Pure DAG state functions for task propagation.

All state is stored in the graph layer (RunGraphNode, RunGraphEdge,
RunGraphMutation). The graph mutation WAL is the single source of truth
for DAG execution state.

RunTaskStateEvent is no longer written or read by this module.
"""

from uuid import UUID

from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinitionTask,
    ExperimentDefinitionTaskDependency,
)
from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphNode
from ergon_core.core.persistence.graph.status_conventions import (
    CANCELLED,
    EDGE_INVALIDATED,
    EDGE_SATISFIED,
    FAILED,
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


def _update_task_status(
    session: Session,
    run_id: UUID,
    task_id: UUID,
    new_status: str,
    *,
    graph_repo: WorkflowGraphRepository,
    graph_lookup: GraphNodeLookup,
    event_metadata: dict[str, object] | None = None,
) -> None:
    node_id = graph_lookup.node_id(task_id)
    if node_id is None:
        return
    reason = None
    if event_metadata and "error" in event_metadata:
        reason = str(event_metadata["error"])
    graph_repo.update_node_status(
        session,
        run_id=run_id,
        node_id=node_id,
        new_status=new_status,
        meta=MutationMeta(actor="system:propagation", reason=reason),
    )


def mark_task_ready(
    session: Session,
    run_id: UUID,
    task_id: UUID,
    *,
    graph_repo: WorkflowGraphRepository,
    graph_lookup: GraphNodeLookup,
) -> None:
    _update_task_status(
        session,
        run_id,
        task_id,
        TaskExecutionStatus.PENDING,
        graph_repo=graph_repo,
        graph_lookup=graph_lookup,
    )


def mark_task_running(
    session: Session,
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID,
    *,
    graph_repo: WorkflowGraphRepository,
    graph_lookup: GraphNodeLookup,
) -> None:
    _update_task_status(
        session,
        run_id,
        task_id,
        TaskExecutionStatus.RUNNING,
        graph_repo=graph_repo,
        graph_lookup=graph_lookup,
    )


def mark_task_completed(
    session: Session,
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID,
    *,
    graph_repo: WorkflowGraphRepository,
    graph_lookup: GraphNodeLookup,
) -> None:
    _update_task_status(
        session,
        run_id,
        task_id,
        TaskExecutionStatus.COMPLETED,
        graph_repo=graph_repo,
        graph_lookup=graph_lookup,
    )


def mark_task_failed(
    session: Session,
    run_id: UUID,
    task_id: UUID,
    error: str,
    *,
    execution_id: UUID | None = None,
    graph_repo: WorkflowGraphRepository,
    graph_lookup: GraphNodeLookup,
) -> None:
    _update_task_status(
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


def get_current_task_status(
    session: Session,
    run_id: UUID,
    task_id: UUID,
    *,
    graph_lookup: GraphNodeLookup,
) -> str | None:
    """Return the current status for a task in this run."""
    node_id = graph_lookup.node_id(task_id)
    if node_id is None:
        return None
    row = session.exec(
        select(RunGraphNode.status).where(
            RunGraphNode.id == node_id,
            RunGraphNode.run_id == run_id,
        )
    ).first()
    return row


def get_initial_ready_tasks(
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
        mark_task_ready(
            session,
            run_id,
            tid,
            graph_repo=graph_repo,
            graph_lookup=graph_lookup,
        )

    session.commit()
    return ready_ids


# ---------------------------------------------------------------------------
# Propagation
# ---------------------------------------------------------------------------


def on_task_completed(
    session: Session,
    run_id: UUID,
    definition_id: UUID,
    task_id: UUID,
    execution_id: UUID,
    *,
    graph_repo: WorkflowGraphRepository,
    graph_lookup: GraphNodeLookup,
) -> list[UUID]:
    """Mark task completed, resolve edges, find and mark newly-ready dependents."""
    mark_task_completed(
        session,
        run_id,
        task_id,
        execution_id,
        graph_repo=graph_repo,
        graph_lookup=graph_lookup,
    )

    dependent_edges_stmt = select(ExperimentDefinitionTaskDependency).where(
        ExperimentDefinitionTaskDependency.experiment_definition_id == definition_id,
        ExperimentDefinitionTaskDependency.depends_on_task_id == task_id,
    )
    dependent_edges = list(session.exec(dependent_edges_stmt).all())

    candidate_task_ids = {e.task_id for e in dependent_edges}

    newly_ready: list[UUID] = []
    for candidate_id in candidate_task_ids:
        all_deps_stmt = select(ExperimentDefinitionTaskDependency.depends_on_task_id).where(
            ExperimentDefinitionTaskDependency.experiment_definition_id == definition_id,
            ExperimentDefinitionTaskDependency.task_id == candidate_id,
        )
        dep_task_ids = list(session.exec(all_deps_stmt).all())

        if all(
            get_current_task_status(
                session,
                run_id,
                dep_id,
                graph_lookup=graph_lookup,
            )
            == TaskExecutionStatus.COMPLETED
            for dep_id in dep_task_ids
        ):
            # Update resolved edges to "satisfied"
            for dep_id in dep_task_ids:
                edge_id = graph_lookup.edge_id(dep_id, candidate_id)
                if edge_id:
                    graph_repo.update_edge_status(
                        session,
                        run_id=run_id,
                        edge_id=edge_id,
                        new_status="satisfied",
                        meta=_PROPAGATION_META,
                    )

            mark_task_ready(
                session,
                run_id,
                candidate_id,
                graph_repo=graph_repo,
                graph_lookup=graph_lookup,
            )
            newly_ready.append(candidate_id)

    session.commit()
    return newly_ready


# ---------------------------------------------------------------------------
# Terminal-state checks
# ---------------------------------------------------------------------------


def is_workflow_complete(session: Session, run_id: UUID, definition_id: UUID) -> bool:
    """True when every graph node for this run has reached COMPLETED."""
    statuses = list(
        session.exec(select(RunGraphNode.status).where(RunGraphNode.run_id == run_id)).all()
    )
    if not statuses:
        return True
    return all(s == TaskExecutionStatus.COMPLETED for s in statuses)


def is_workflow_failed(session: Session, run_id: UUID, definition_id: UUID) -> bool:
    """True when any graph node for this run has reached FAILED."""
    statuses = list(
        session.exec(select(RunGraphNode.status).where(RunGraphNode.run_id == run_id)).all()
    )
    return any(s == TaskExecutionStatus.FAILED for s in statuses)


# ---------------------------------------------------------------------------
# Graph-native write helpers (no GraphNodeLookup)
# ---------------------------------------------------------------------------


def mark_task_running_by_node(
    session: Session,
    run_id: UUID,
    node_id: UUID,
    execution_id: UUID,
    *,
    graph_repo: WorkflowGraphRepository,
) -> None:
    graph_repo.update_node_status(
        session,
        run_id=run_id,
        node_id=node_id,
        new_status=TaskExecutionStatus.RUNNING,
        meta=MutationMeta(
            actor="system:propagation",
            reason=f"execution {execution_id} running",
        ),
    )


def mark_task_completed_by_node(
    session: Session,
    run_id: UUID,
    node_id: UUID,
    execution_id: UUID,
    *,
    graph_repo: WorkflowGraphRepository,
) -> None:
    graph_repo.update_node_status(
        session,
        run_id=run_id,
        node_id=node_id,
        new_status=TaskExecutionStatus.COMPLETED,
        meta=MutationMeta(
            actor="system:propagation",
            reason=f"execution {execution_id} completed",
        ),
    )


def mark_task_failed_by_node(
    session: Session,
    run_id: UUID,
    node_id: UUID,
    error: str,
    *,
    execution_id: UUID | None = None,
    graph_repo: WorkflowGraphRepository,
) -> None:
    graph_repo.update_node_status(
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


def on_task_completed_by_node(
    session: Session,
    run_id: UUID,
    node_id: UUID,
    execution_id: UUID,
    *,
    graph_repo: WorkflowGraphRepository,
) -> list[UUID]:
    """Process completion of a graph node. Returns newly-ready node_ids.

    .. deprecated:: Use on_task_completed_or_failed for new code.

    Walks RunGraphEdge (not ExperimentDefinitionTaskDependency) so it
    works for both static and dynamic tasks.
    """
    graph_repo.update_node_status(
        session,
        run_id=run_id,
        node_id=node_id,
        new_status=TaskExecutionStatus.COMPLETED,
        meta=MutationMeta(
            actor="system:propagation",
            reason=f"execution {execution_id} completed",
        ),
    )

    outgoing = list(
        session.exec(
            select(RunGraphEdge).where(
                RunGraphEdge.run_id == run_id,
                RunGraphEdge.source_node_id == node_id,
            )
        ).all()
    )
    candidate_node_ids = {e.target_node_id for e in outgoing}

    newly_ready: list[UUID] = []
    for candidate_id in candidate_node_ids:
        candidate_node = session.get(RunGraphNode, candidate_id)
        if candidate_node is None or candidate_node.status != TaskExecutionStatus.PENDING:
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
        if all(n is not None and n.status in TERMINAL_STATUSES for n in source_nodes):
            graph_repo.update_node_status(
                session,
                run_id=run_id,
                node_id=candidate_id,
                new_status=TaskExecutionStatus.PENDING,
                meta=MutationMeta(
                    actor="system:propagation",
                    reason=f"all dependencies satisfied after {node_id}",
                ),
            )
            newly_ready.append(candidate_id)

    session.commit()
    return newly_ready


def on_task_completed_or_failed(
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
    - FAILED / CANCELLED: outgoing edges become INVALIDATED; targets are
      reported as invalidated (caller emits task/cancelled).

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
        graph_repo.update_edge_status(
            session,
            run_id=run_id,
            edge_id=edge.id,
            new_status=edge_status,
            meta=_PROPAGATION_META,
        )

    candidate_node_ids = {e.target_node_id for e in outgoing}

    newly_ready: list[UUID] = []
    invalidated: list[UUID] = []

    for candidate_id in candidate_node_ids:
        candidate_node = session.get(RunGraphNode, candidate_id)
        if candidate_node is None or candidate_node.status in TERMINAL_STATUSES:
            continue

        if not is_success:
            # Source failed/cancelled — mark target as invalidated
            graph_repo.update_node_status(
                session,
                run_id=run_id,
                node_id=candidate_id,
                new_status=CANCELLED,
                meta=MutationMeta(
                    actor="system:propagation",
                    reason=f"dependency {node_id} {terminal_status}",
                ),
                only_if_not_terminal=True,
            )
            invalidated.append(candidate_id)
            continue

        # Source completed — check if ALL incoming edges are satisfied
        if candidate_node.status != TaskExecutionStatus.PENDING:
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
            graph_repo.update_node_status(
                session,
                run_id=run_id,
                node_id=candidate_id,
                new_status=TaskExecutionStatus.PENDING,
                meta=MutationMeta(
                    actor="system:propagation",
                    reason=f"all dependencies satisfied after {node_id}",
                ),
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


def is_workflow_failed_v2(session: Session, run_id: UUID) -> bool:
    """True when any graph node for this run has reached FAILED."""
    statuses = list(
        session.exec(select(RunGraphNode.status).where(RunGraphNode.run_id == run_id)).all()
    )
    return any(s == TaskExecutionStatus.FAILED for s in statuses)
