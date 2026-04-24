"""Shared helpers for restart integration tests."""

from uuid import UUID

from sqlmodel import select

from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunRecord


def cleanup_run(run_id: UUID, defn_id: UUID) -> None:
    with get_session() as session:
        for mut in session.exec(
            select(RunGraphMutation).where(RunGraphMutation.run_id == run_id)
        ).all():
            session.delete(mut)
        for edge in session.exec(select(RunGraphEdge).where(RunGraphEdge.run_id == run_id)).all():
            session.delete(edge)
        for nd in session.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).all():
            session.delete(nd)
        run_row = session.get(RunRecord, run_id)
        if run_row is not None:
            session.delete(run_row)
        defn_row = session.get(ExperimentDefinition, defn_id)
        if defn_row is not None:
            session.delete(defn_row)
        session.commit()


def get_edge_status(session, run_id: UUID, source_id: UUID, target_id: UUID) -> str:  # type: ignore[no-untyped-def]
    edge = session.exec(
        select(RunGraphEdge).where(
            RunGraphEdge.run_id == run_id,
            RunGraphEdge.source_node_id == source_id,
            RunGraphEdge.target_node_id == target_id,
        )
    ).first()
    assert edge is not None, f"No edge from {source_id} to {target_id}"
    session.refresh(edge)
    return edge.status
