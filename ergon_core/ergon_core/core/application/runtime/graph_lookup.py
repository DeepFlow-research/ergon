"""Batch-loaded run graph task lookup for propagation."""

from uuid import UUID

from ergon_core.core.persistence.graph.models import SampleGraphEdge, SampleGraphNode
from sqlmodel import Session, select


class GraphNodeLookup:
    """Caches task and edge ids for one run."""

    def __init__(self, session: Session, sample_id: UUID) -> None:
        task_ids = session.exec(
            select(SampleGraphNode.task_id).where(SampleGraphNode.sample_id == sample_id)
        ).all()
        self._tasks: frozenset[UUID] = frozenset(task_ids)

        edge_rows = session.exec(
            select(
                SampleGraphEdge.id, SampleGraphEdge.source_task_id, SampleGraphEdge.target_task_id
            ).where(SampleGraphEdge.sample_id == sample_id)
        ).all()
        self._edges: dict[tuple[UUID, UUID], UUID] = {
            (src, tgt): eid for eid, src, tgt in edge_rows
        }

    def has_task(self, task_id: UUID) -> bool:
        """Return whether the run graph contains the runtime task id."""
        return task_id in self._tasks

    def edge_id_by_nodes(self, source_task_id: UUID, target_task_id: UUID) -> UUID | None:
        """Get edge ID by source and target task IDs."""
        return self._edges.get((source_task_id, target_task_id))

    def edge_id(self, source_task_id: UUID, target_task_id: UUID) -> UUID | None:
        """Get edge ID by source and target task IDs."""
        if not self.has_task(source_task_id) or not self.has_task(target_task_id):
            return None
        return self.edge_id_by_nodes(source_task_id, target_task_id)
