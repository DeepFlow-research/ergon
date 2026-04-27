"""Shared polling and assertion helpers for propagation integration tests."""

import time
from uuid import UUID

from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import ExperimentRecord, RunRecord
from sqlmodel import Session, select


def poll_until(condition, *, timeout: float = 30, interval: float = 0.5) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(interval)
    raise TimeoutError("poll_until timed out")


def get_node(session: Session, node_id: UUID) -> RunGraphNode:
    node = session.get(RunGraphNode, node_id)
    session.refresh(node)
    return node


def get_node_status(session: Session, node_id: UUID) -> str:
    node = session.get(RunGraphNode, node_id)
    session.refresh(node)
    return node.status


def get_wal_entries(session: Session, node_id: UUID) -> list[RunGraphMutation]:
    return list(
        session.exec(select(RunGraphMutation).where(RunGraphMutation.target_id == node_id)).all()
    )


def assert_wal_has_status(
    session: Session,
    node_id: UUID,
    status: str,
    *,
    cause_contains: str | None = None,
) -> None:
    entries = get_wal_entries(session, node_id)
    matching = [e for e in entries if e.new_value.get("status") == status]
    assert matching, (
        f"No WAL entry with status={status!r} for node {node_id}. "
        f"Entries: {[e.new_value for e in entries]}"
    )
    if cause_contains is not None:
        assert any(e.reason and cause_contains in e.reason for e in matching), (
            f"No WAL entry with cause containing {cause_contains!r} for node {node_id}"
        )


def assert_cross_cutting_invariants(session: Session, run_id: UUID) -> None:
    """Basic invariants that should hold after any settled state."""
    nodes = list(session.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).all())
    for node in nodes:
        session.refresh(node)
        entries = get_wal_entries(session, node.id)
        assert entries, f"Node {node.id} ({node.task_slug}) has no WAL entries"


# ---------------------------------------------------------------------------
# Graph construction helpers
# ---------------------------------------------------------------------------


def make_experiment_definition(session: Session) -> ExperimentDefinition:
    """Create a minimal ExperimentDefinition row for test scaffolding."""
    defn = ExperimentDefinition(benchmark_type="ci-propagation-test")
    session.add(defn)
    session.flush()
    session.refresh(defn)
    return defn


def make_run(session: Session, definition_id: UUID) -> RunRecord:
    """Create a minimal RunRecord row for test scaffolding."""
    experiment = ExperimentRecord(
        name="ci propagation experiment",
        benchmark_type="ci-propagation-test",
        sample_count=1,
        sample_selection_json={"instance_keys": ["test"]},
        default_worker_team_json={"primary": "test-worker"},
        design_json={},
        metadata_json={},
        status="running",
    )
    session.add(experiment)
    session.flush()
    run = RunRecord(
        experiment_id=experiment.id,
        workflow_definition_id=definition_id,
        benchmark_type="ci-propagation-test",
        instance_key="test",
        worker_team_json={"primary": "test-worker"},
        status=RunStatus.EXECUTING,
    )
    session.add(run)
    session.flush()
    session.refresh(run)
    return run


def make_node(
    session: Session,
    run_id: UUID,
    *,
    task_slug: str,
    status: str = "pending",
    parent_node_id: UUID | None = None,
    level: int = 0,
) -> RunGraphNode:
    """Create a RunGraphNode row for test scaffolding."""
    node = RunGraphNode(
        run_id=run_id,
        instance_key="test",
        task_slug=task_slug,
        description=f"Test node: {task_slug}",
        status=status,
        parent_node_id=parent_node_id,
        level=level,
    )
    session.add(node)
    session.flush()
    session.refresh(node)
    return node


def make_edge(
    session: Session,
    run_id: UUID,
    *,
    source_node_id: UUID,
    target_node_id: UUID,
    status: str = "pending",
) -> RunGraphEdge:
    """Create a RunGraphEdge row for test scaffolding."""
    edge = RunGraphEdge(
        run_id=run_id,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        status=status,
    )
    session.add(edge)
    session.flush()
    session.refresh(edge)
    return edge


def seed_linear_chain(
    session: Session,
    run_id: UUID,
    slugs: list[str],
    *,
    first_status: str = "running",
    rest_status: str = "pending",
) -> list[RunGraphNode]:
    """Create a linear chain of nodes A→B→C… with edges between them.

    The first node defaults to 'running'; all others default to 'pending'.
    Returns nodes in order [A, B, C, ...].
    """
    nodes: list[RunGraphNode] = []
    for i, slug in enumerate(slugs):
        status = first_status if i == 0 else rest_status
        node = make_node(session, run_id, task_slug=slug, status=status)
        nodes.append(node)

    for i in range(len(nodes) - 1):
        make_edge(session, run_id, source_node_id=nodes[i].id, target_node_id=nodes[i + 1].id)

    session.commit()
    return nodes
