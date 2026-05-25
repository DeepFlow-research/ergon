"""Workflow propagation service helpers.

All state is stored in the graph layer (SampleGraphNode, SampleGraphEdge,
SampleGraphMutation). The graph mutation WAL is the single source of truth
for DAG execution state.
"""

from uuid import UUID

from ergon_core.core.shared.json_types import JsonObject
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinitionTask,
    ExperimentDefinitionTaskDependency,
)
from ergon_core.core.application.runtime import status as graph_status
from ergon_core.core.persistence.graph.models import SampleGraphEdge, SampleGraphNode
from ergon_core.core.application.runtime.models import MutationMeta
from ergon_core.core.application.runtime.graph_lookup import GraphNodeLookup
from ergon_core.core.application.runtime.graph_repository import RuntimeGraphRepository
from sqlmodel import Session, select

_PROPAGATION_META = MutationMeta(actor="system:propagation")


async def _update_task_status(
    session: Session,
    sample_id: UUID,
    task_id: UUID,
    new_status: str,
    *,
    graph_repo: RuntimeGraphRepository,
    graph_lookup: GraphNodeLookup,
    event_metadata: JsonObject | None = None,
) -> None:
    if not graph_lookup.has_task(task_id):
        return
    reason = None
    if event_metadata and "error" in event_metadata:
        reason = str(event_metadata["error"])
    await graph_repo.update_node_status(
        session,
        sample_id=sample_id,
        task_id=task_id,
        new_status=new_status,
        meta=MutationMeta(actor="system:propagation", reason=reason),
    )


async def mark_task_ready(
    session: Session,
    sample_id: UUID,
    task_id: UUID,
    *,
    graph_repo: RuntimeGraphRepository,
    graph_lookup: GraphNodeLookup,
) -> None:
    await _update_task_status(
        session,
        sample_id,
        task_id,
        graph_status.PENDING,
        graph_repo=graph_repo,
        graph_lookup=graph_lookup,
    )


async def mark_task_running(
    session: Session,
    sample_id: UUID,
    task_id: UUID,
    execution_id: UUID,
    *,
    graph_repo: RuntimeGraphRepository,
    graph_lookup: GraphNodeLookup,
) -> None:
    await _update_task_status(
        session,
        sample_id,
        task_id,
        graph_status.RUNNING,
        graph_repo=graph_repo,
        graph_lookup=graph_lookup,
    )


async def mark_task_failed(
    session: Session,
    sample_id: UUID,
    task_id: UUID,
    error: str,
    *,
    execution_id: UUID | None = None,
    graph_repo: RuntimeGraphRepository,
    graph_lookup: GraphNodeLookup,
) -> None:
    await _update_task_status(
        session,
        sample_id,
        task_id,
        graph_status.FAILED,
        graph_repo=graph_repo,
        graph_lookup=graph_lookup,
        event_metadata={"error": error},
    )


async def get_initial_ready_tasks(
    session: Session,
    sample_id: UUID,
    definition_id: UUID,
    *,
    graph_repo: RuntimeGraphRepository,
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
            sample_id,
            task_id,
            graph_repo=graph_repo,
            graph_lookup=graph_lookup,
        )

    session.commit()
    return ready_ids


async def mark_task_failed_by_node(
    session: Session,
    sample_id: UUID,
    task_id: UUID,
    error: str,
    *,
    execution_id: UUID | None = None,
    graph_repo: RuntimeGraphRepository,
) -> None:
    del execution_id
    await graph_repo.update_node_status(
        session,
        sample_id=sample_id,
        task_id=task_id,
        new_status=graph_status.FAILED,
        meta=MutationMeta(
            actor="system:propagation",
            reason=error,
        ),
    )


# TODO: as per the experiments design comment, feels like alot of this would benefit from being a service or repository method?
async def _block_successors_bfs(
    session: Session,
    sample_id: UUID,
    seed_task_ids: set[UUID],
    *,
    failed_task_id: UUID,
    terminal_status: str,
    graph_repo: RuntimeGraphRepository,
) -> None:
    """Propagate BLOCKED through the reachable downstream graph."""
    queue = list(seed_task_ids)
    while queue:
        target_id = queue.pop()
        target_node = session.get(SampleGraphNode, (sample_id, target_id))
        if target_node is None:
            continue
        if target_node.status == graph_status.RUNNING:
            continue
        if target_node.status in graph_status.TERMINAL_STATUSES:
            continue

        applied = await graph_repo.update_node_status(
            session,
            sample_id=sample_id,
            task_id=target_id,
            new_status=graph_status.BLOCKED,
            meta=MutationMeta(
                actor="system:propagation",
                reason=f"dependency {failed_task_id} {terminal_status}",
            ),
            only_if_not_terminal=True,
        )

        if applied:
            target_outgoing = list(
                session.exec(
                    select(SampleGraphEdge).where(
                        SampleGraphEdge.sample_id == sample_id,
                        SampleGraphEdge.source_task_id == target_id,
                    )
                ).all()
            )
            for edge in target_outgoing:
                await graph_repo.update_edge_status(
                    session,
                    sample_id=sample_id,
                    edge_id=edge.id,
                    new_status=graph_status.EDGE_INVALIDATED,
                    meta=_PROPAGATION_META,
                )
                queue.append(edge.target_task_id)


def _dependency_free_children(session: Session, sample_id: UUID, task_id: UUID) -> set[UUID]:
    child_ids: set[UUID] = set()
    containment_children = list(
        session.exec(
            select(SampleGraphNode).where(
                SampleGraphNode.sample_id == sample_id,
                SampleGraphNode.parent_task_id == task_id,
            )
        ).all()
    )
    for child in containment_children:
        has_incoming_edges = session.exec(
            select(SampleGraphEdge.id)
            .where(SampleGraphEdge.sample_id == sample_id)
            .where(SampleGraphEdge.target_task_id == child.task_id)
        ).first()
        if has_incoming_edges is None:
            child_ids.add(child.task_id)
    return child_ids


async def on_task_completed_or_failed(
    session: Session,
    sample_id: UUID,
    task_id: UUID,
    terminal_status: str,
    *,
    graph_repo: RuntimeGraphRepository,
) -> list[UUID]:
    """Handle a task reaching COMPLETED, FAILED, or CANCELLED."""
    is_success = terminal_status == graph_status.COMPLETED

    outgoing = list(
        session.exec(
            select(SampleGraphEdge).where(
                SampleGraphEdge.sample_id == sample_id,
                SampleGraphEdge.source_task_id == task_id,
            )
        ).all()
    )

    edge_status = graph_status.EDGE_SATISFIED if is_success else graph_status.EDGE_INVALIDATED
    for edge in outgoing:
        await graph_repo.update_edge_status(
            session,
            sample_id=sample_id,
            edge_id=edge.id,
            new_status=edge_status,
            meta=_PROPAGATION_META,
        )

    candidate_task_ids = {edge.target_task_id for edge in outgoing}
    if is_success:
        candidate_task_ids.update(_dependency_free_children(session, sample_id, task_id))
    newly_ready: list[UUID] = []

    if not is_success:
        await _block_successors_bfs(
            session,
            sample_id=sample_id,
            seed_task_ids=candidate_task_ids,
            failed_task_id=task_id,
            terminal_status=terminal_status,
            graph_repo=graph_repo,
        )
        session.commit()
        return newly_ready

    for candidate_id in candidate_task_ids:
        candidate_node = session.get(SampleGraphNode, (sample_id, candidate_id))
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
                select(SampleGraphEdge).where(
                    SampleGraphEdge.sample_id == sample_id,
                    SampleGraphEdge.target_task_id == candidate_id,
                )
            ).all()
        )

        source_nodes = [
            session.get(SampleGraphNode, (sample_id, edge.source_task_id)) for edge in incoming
        ]
        if all(node is not None and node.status == graph_status.COMPLETED for node in source_nodes):
            reason = (
                f"all dependencies satisfied after {task_id}"
                if is_pending
                else f"re-activating cancelled subtask after {task_id}"
            )
            await graph_repo.update_node_status(
                session,
                sample_id=sample_id,
                task_id=candidate_id,
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


def is_workflow_complete_v2(session: Session, sample_id: UUID) -> bool:
    """Every node terminal; zero FAILED. CANCELLED is neutral."""
    statuses = list(
        session.exec(
            select(SampleGraphNode.status).where(SampleGraphNode.sample_id == sample_id)
        ).all()
    )
    if not statuses:
        return True
    return all(status in graph_status.TERMINAL_STATUSES for status in statuses) and not any(
        status == graph_status.FAILED for status in statuses
    )


_SETTLED_STATUSES = graph_status.TERMINAL_STATUSES | frozenset({graph_status.BLOCKED})


def is_workflow_failed_v2(session: Session, sample_id: UUID) -> bool:
    """All nodes settled and at least one FAILED."""
    statuses = list(
        session.exec(
            select(SampleGraphNode.status).where(SampleGraphNode.sample_id == sample_id)
        ).all()
    )
    if not statuses:
        return False
    all_settled = all(status in _SETTLED_STATUSES for status in statuses)
    return all_settled and any(status == graph_status.FAILED for status in statuses)
