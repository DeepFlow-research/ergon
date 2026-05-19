"""Batch-loaded run graph id lookup for propagation."""

from uuid import UUID

from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphNode
from sqlmodel import Session, select


class GraphNodeLookup:
    """Caches node and edge ids for one run."""

    def __init__(self, session: Session, run_id: UUID) -> None:
        node_rows = session.exec(select(RunGraphNode.id).where(RunGraphNode.run_id == run_id)).all()
        self._nodes: dict[UUID, UUID] = {node_id: node_id for node_id in node_rows}

        edge_rows = session.exec(
            select(RunGraphEdge.id, RunGraphEdge.source_task_id, RunGraphEdge.target_task_id).where(
                RunGraphEdge.run_id == run_id
            )
        ).all()
        self._edges: dict[tuple[UUID, UUID], UUID] = {
            (src, tgt): eid for eid, src, tgt in edge_rows
        }

    def node_id(self, task_id: UUID) -> UUID | None:
        """Get the run graph node ID for a task ID."""
        return self._nodes.get(task_id)

    def edge_id_by_nodes(self, source_task_id: UUID, target_task_id: UUID) -> UUID | None:
        """Get edge ID by source and target node IDs."""
        return self._edges.get((source_task_id, target_task_id))

    def edge_id(self, source_task_id: UUID, target_task_id: UUID) -> UUID | None:
        """Get edge ID by source and target task IDs."""
        src = self.node_id(source_task_id)
        tgt = self.node_id(target_task_id)
        if src is None or tgt is None:
            return None
        return self.edge_id_by_nodes(src, tgt)
