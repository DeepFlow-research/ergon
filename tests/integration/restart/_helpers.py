"""Shared helpers for restart integration tests."""

from uuid import UUID

from ergon_core.core.persistence.graph.models import SampleGraphEdge, SampleGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import SampleRecord
from sqlmodel import select
from tests.integration.propagation._helpers import delete_typed_sample_wal


def cleanup_run(sample_id: UUID) -> None:
    with get_session() as session:
        delete_typed_sample_wal(session, sample_id)
        for edge in session.exec(
            select(SampleGraphEdge).where(SampleGraphEdge.sample_id == sample_id)
        ).all():
            session.delete(edge)
        nodes = list(
            session.exec(
                select(SampleGraphNode).where(SampleGraphNode.sample_id == sample_id)
            ).all()
        )
        remaining = {node.task_id: node for node in nodes}
        while remaining:
            parent_ids = {
                node.parent_task_id
                for node in remaining.values()
                if node.parent_task_id is not None
            }
            leaves = [node for node in remaining.values() if node.task_id not in parent_ids]
            for node in leaves:
                session.delete(node)
                remaining.pop(node.task_id)
            session.flush()
        run_row = session.get(SampleRecord, sample_id)
        if run_row is not None:
            session.delete(run_row)
        session.commit()


def get_edge_status(session, sample_id: UUID, source_id: UUID, target_id: UUID) -> str:  # type: ignore[no-untyped-def]
    edge = session.exec(
        select(SampleGraphEdge).where(
            SampleGraphEdge.sample_id == sample_id,
            SampleGraphEdge.source_task_id == source_id,
            SampleGraphEdge.target_task_id == target_id,
        )
    ).first()
    assert edge is not None, f"No edge from {source_id} to {target_id}"
    session.refresh(edge)
    return edge.status
