"""Batch-loaded mapping from definition task/edge IDs to run graph IDs.

Constructed once per propagation call. Two queries at init time,
zero per-node queries during dependency resolution.
"""

from uuid import UUID

from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphNode
from sqlmodel import Session, select


class GraphNodeLookup:
    """Maps definition_task_id to run_graph_node.id for one run.

    Also caches edge lookups (source_node_id, target_node_id) -> edge_id.
    """

    def __init__(self, session: Session, run_id: UUID) -> None:
        node_rows = session.exec(
            select(RunGraphNode.id, RunGraphNode.definition_task_id).where(
                RunGraphNode.run_id == run_id
            )
        ).all()
        self._nodes: dict[UUID, UUID] = {
            defn_id: node_id for node_id, defn_id in node_rows if defn_id is not None
        }

        edge_rows = session.exec(
            select(RunGraphEdge.id, RunGraphEdge.source_node_id, RunGraphEdge.target_node_id).where(
                RunGraphEdge.run_id == run_id
            )
        ).all()
        self._edges: dict[tuple[UUID, UUID], UUID] = {
            (src, tgt): eid for eid, src, tgt in edge_rows
        }

    def node_id(self, definition_task_id: UUID) -> UUID | None:
        """Get the run graph node ID for a definition task ID."""
        return self._nodes.get(definition_task_id)

    def edge_id_by_nodes(self, source_node_id: UUID, target_node_id: UUID) -> UUID | None:
        """Get edge ID by source and target node IDs."""
        return self._edges.get((source_node_id, target_node_id))

    def edge_id(self, source_defn_id: UUID, target_defn_id: UUID) -> UUID | None:
        """Get edge ID by source and target definition task IDs."""
        src = self.node_id(source_defn_id)
        tgt = self.node_id(target_defn_id)
        if src is None or tgt is None:
            return None
        return self.edge_id_by_nodes(src, tgt)
