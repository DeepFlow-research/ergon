"""Batch-loaded mapping from authored task IDs to run graph task IDs.

Constructed once per propagation call. Two queries at init time,
zero per-node queries during dependency resolution.
"""

from uuid import UUID

from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphNode
from sqlmodel import Session, select


class GraphNodeLookup:
    """Maps authored task IDs to run-graph task IDs for one run.

    Also caches edge lookups (source_task_id, target_task_id) -> edge_id.
    """

    def __init__(self, session: Session, run_id: UUID) -> None:
        node_rows = session.exec(
            select(RunGraphNode.task_id).where(RunGraphNode.run_id == run_id)
        ).all()
        self._nodes: dict[UUID, UUID] = {task_id: task_id for task_id in node_rows}

        edge_rows = session.exec(
            select(RunGraphEdge.id, RunGraphEdge.source_task_id, RunGraphEdge.target_task_id).where(
                RunGraphEdge.run_id == run_id
            )
        ).all()
        self._edges: dict[tuple[UUID, UUID], UUID] = {
            (src, tgt): eid for eid, src, tgt in edge_rows
        }

    def node_id(self, definition_task_id: UUID) -> UUID | None:
        """Get the run graph task ID for an authored task ID."""
        return self._nodes.get(definition_task_id)

    def edge_id_by_nodes(self, source_node_id: UUID, target_node_id: UUID) -> UUID | None:
        """Get edge ID by source and target task IDs."""
        return self._edges.get((source_node_id, target_node_id))

    def edge_id(self, source_defn_id: UUID, target_defn_id: UUID) -> UUID | None:
        """Get edge ID by source and target authored task IDs."""
        src = self.node_id(source_defn_id)
        tgt = self.node_id(target_defn_id)
        if src is None or tgt is None:
            return None
        return self.edge_id_by_nodes(src, tgt)
