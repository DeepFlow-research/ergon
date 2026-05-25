"""Shared polling and assertion helpers for propagation integration tests."""

import time
from uuid import UUID

from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import SampleGraphEdge, SampleGraphNode
from ergon_core.core.persistence.samples.models import (
    SampleAnnotationEventRow,
    SampleEdgeEventRow,
    SampleEvaluatorEventRow,
    SampleSandboxEventRow,
    SampleStatusEventRow,
    SampleTaskEventRow,
    SampleWorkerEventRow,
)
from ergon_core.core.application.runtime.status import TERMINAL_STATUSES
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import SampleStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord
from sqlmodel import Session, select


def poll_until(condition, *, timeout: float = 30, interval: float = 0.5) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(interval)
    raise TimeoutError("poll_until timed out")


def get_node(session: Session, task_id: UUID) -> SampleGraphNode:
    node = session.exec(select(SampleGraphNode).where(SampleGraphNode.task_id == task_id)).one()
    session.refresh(node)
    return node


def get_node_status(session: Session, task_id: UUID) -> str:
    node = get_node(session, task_id)
    session.refresh(node)
    return node.status


SAMPLE_WAL_MODELS = (
    SampleAnnotationEventRow,
    SampleEdgeEventRow,
    SampleEvaluatorEventRow,
    SampleSandboxEventRow,
    SampleStatusEventRow,
    SampleTaskEventRow,
    SampleWorkerEventRow,
)


def delete_typed_sample_wal(session: Session, sample_id: UUID) -> None:
    for model in SAMPLE_WAL_MODELS:
        for row in session.exec(select(model).where(model.sample_id == sample_id)).all():
            session.delete(row)


def get_wal_entries(session: Session, task_id: UUID) -> list[SampleTaskEventRow]:
    return list(
        session.exec(select(SampleTaskEventRow).where(SampleTaskEventRow.task_id == task_id)).all()
    )


def assert_wal_has_status(
    session: Session,
    task_id: UUID,
    status: str,
    *,
    cause_contains: str | None = None,
) -> None:
    entries = get_wal_entries(session, task_id)
    matching = [e for e in entries if e.status == status or e.payload_json.get("status") == status]
    assert matching, (
        f"No WAL entry with status={status!r} for node {task_id}. "
        f"Entries: {[e.payload_json for e in entries]}"
    )
    if cause_contains is not None:
        assert any(
            e.actor and cause_contains in e.actor or cause_contains in str(e.payload_json)
            for e in matching
        ), f"No WAL entry with cause containing {cause_contains!r} for node {task_id}"


def assert_cross_cutting_invariants(session: Session, sample_id: UUID) -> None:
    """Basic invariants that should hold after any settled state."""
    nodes = list(
        session.exec(select(SampleGraphNode).where(SampleGraphNode.sample_id == sample_id)).all()
    )
    for node in nodes:
        session.refresh(node)
        entries = get_wal_entries(session, node.task_id)
        assert entries, f"Node {node.task_id} ({node.task_slug}) has no WAL entries"


# ---------------------------------------------------------------------------
# Graph construction helpers
# ---------------------------------------------------------------------------


def make_experiment_definition(session: Session) -> ExperimentDefinition:
    """Create a minimal ExperimentDefinition row for test scaffolding."""
    defn = ExperimentDefinition(benchmark_type="ci-propagation-test", name="ci-propagation-test")
    session.add(defn)
    session.flush()
    session.refresh(defn)
    return defn


def make_run(session: Session, definition_id: UUID) -> SampleRecord:
    """Create a minimal SampleRecord row for test scaffolding."""
    run = SampleRecord(
        definition_id=definition_id,
        workflow_definition_id=definition_id,
        benchmark_type="ci-propagation-test",
        instance_key="test",
        status=SampleStatus.EXECUTING,
    )
    session.add(run)
    session.flush()
    session.refresh(run)
    return run


def make_node(
    session: Session,
    sample_id: UUID,
    *,
    task_slug: str,
    status: str = "pending",
    parent_task_id: UUID | None = None,
    level: int = 0,
) -> SampleGraphNode:
    """Create a SampleGraphNode row for test scaffolding."""
    node = SampleGraphNode(
        sample_id=sample_id,
        instance_key="test",
        task_slug=task_slug,
        description=f"Test node: {task_slug}",
        status=status,
        parent_task_id=parent_task_id,
        level=level,
    )
    session.add(node)
    session.flush()
    session.refresh(node)
    return node


def make_edge(
    session: Session,
    sample_id: UUID,
    *,
    source_task_id: UUID,
    target_task_id: UUID,
    status: str = "pending",
) -> SampleGraphEdge:
    """Create a SampleGraphEdge row for test scaffolding."""
    edge = SampleGraphEdge(
        sample_id=sample_id,
        source_task_id=source_task_id,
        target_task_id=target_task_id,
        status=status,
    )
    session.add(edge)
    session.flush()
    session.refresh(edge)
    return edge


def seed_linear_chain(
    session: Session,
    sample_id: UUID,
    slugs: list[str],
    *,
    first_status: str = "running",
    rest_status: str = "pending",
) -> list[SampleGraphNode]:
    """Create a linear chain of nodes A→B→C… with edges between them.

    The first node defaults to 'running'; all others default to 'pending'.
    Returns nodes in order [A, B, C, ...].
    """
    nodes: list[SampleGraphNode] = []
    for i, slug in enumerate(slugs):
        status = first_status if i == 0 else rest_status
        node = make_node(session, sample_id, task_slug=slug, status=status)
        nodes.append(node)

    for i in range(len(nodes) - 1):
        make_edge(
            session,
            sample_id,
            source_task_id=nodes[i].task_id,
            target_task_id=nodes[i + 1].task_id,
        )

    session.commit()
    return nodes
