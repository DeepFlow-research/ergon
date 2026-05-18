"""PR 1 focused tests — run-tier task snapshot foundation.

Asserts that `WorkflowGraphRepository.initialize_from_definition`
populates `task_json` and `is_dynamic` correctly, and that `add_node`
can accept dynamic task JSON for graph-native spawns.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from ergon_core.core.application.graph.models import MutationMeta
from ergon_core.core.application.graph.repository import WorkflowGraphRepository
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionInstance,
    ExperimentDefinitionTask,
)
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import (
    BenchmarkDefinitionRecord,
    RunRecord,
)
from pydantic import BaseModel
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


class _EmptyPayload(BaseModel):
    pass


def _session() -> Session:
    # Ensure BenchmarkDefinitionRecord is imported so its table participates in
    # create_all (same pattern as test_graph_worker_identity.py).
    _ = BenchmarkDefinitionRecord
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _seed_definition(session: Session, *, task_slug: str, payload: dict) -> tuple[UUID, UUID, UUID]:
    """Insert a minimal definition with one task and a backing
    BenchmarkDefinitionRecord; return (experiment_id, definition_id, task_id)."""

    experiment_id = uuid4()
    definition_id = uuid4()
    instance_id = uuid4()
    task_id = uuid4()
    session.add_all(
        [
            BenchmarkDefinitionRecord(
                id=experiment_id,
                name="test-experiment",
                benchmark_type="test",
                sample_count=1,
            ),
            ExperimentDefinition(
                id=definition_id, benchmark_type="test", name="test", metadata_json={}
            ),
            ExperimentDefinitionInstance(
                id=instance_id,
                experiment_definition_id=definition_id,
                instance_key="sample-1",
            ),
            ExperimentDefinitionTask(
                id=task_id,
                experiment_definition_id=definition_id,
                instance_id=instance_id,
                task_slug=task_slug,
                description=f"{task_slug} task",
                task_payload_json=payload,
            ),
        ]
    )
    session.commit()
    return experiment_id, definition_id, task_id


def _seed_run(
    session: Session,
    *,
    experiment_id: UUID,
    definition_id: UUID,
    run_id: UUID,
) -> None:
    session.add(
        RunRecord(
            id=run_id,
            experiment_id=experiment_id,
            workflow_definition_id=definition_id,
            benchmark_type="test",
            instance_key="sample-1",
            worker_team_json={},
            status=RunStatus.EXECUTING,
        )
    )
    session.commit()


def test_initialize_from_definition_copies_task_json() -> None:
    session = _session()
    run_id = uuid4()
    experiment_id, definition_id, _task_id = _seed_definition(
        session, task_slug="solve", payload={"problem": "p"}
    )
    _seed_run(
        session,
        experiment_id=experiment_id,
        definition_id=definition_id,
        run_id=run_id,
    )

    repo = WorkflowGraphRepository()
    repo.initialize_from_definition(
        session,
        run_id=run_id,
        definition_id=definition_id,
        initial_node_status="pending",
        initial_edge_status="pending",
        task_payload_model=_EmptyPayload,
        meta=MutationMeta(actor="test", reason="snapshot"),
    )

    rows = session.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).all()
    assert rows, "initialize_from_definition produced no nodes"
    row = rows[0]
    assert row.task_json, "task_json must be populated for static nodes"
    assert row.task_json["task_slug"] == "solve"
    assert row.task_json["task_payload"] == {"problem": "p"}
    assert row.task_json["_type"].endswith(":TaskSpec")
    assert row.task_json["_legacy"]["task_id"]
    assert row.is_dynamic is False


@pytest.mark.asyncio
async def test_graph_repo_node_inflates_task_from_run_tier() -> None:
    """PR 2 invariant: graph_repo.node reads run_graph_nodes.task_json
    and returns a typed RunGraphNodeView with the Task already
    inflated. No definition-tier read; no raw dict in the caller's
    hands."""

    session = _session()
    run_id = uuid4()
    experiment_id, definition_id, _task_id = _seed_definition(
        session, task_slug="solve", payload={"problem": "p"}
    )
    _seed_run(
        session,
        experiment_id=experiment_id,
        definition_id=definition_id,
        run_id=run_id,
    )

    repo = WorkflowGraphRepository()
    # Populate task_json via the PR 1 path so the view has something to
    # inflate.
    repo.initialize_from_definition(
        session,
        run_id=run_id,
        definition_id=definition_id,
        initial_node_status="pending",
        initial_edge_status="pending",
        task_payload_model=_EmptyPayload,
        meta=MutationMeta(actor="test", reason="setup"),
    )
    row = session.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).first()
    assert row is not None

    canonical_task_id = row.task_id or row.id
    view = await repo.node(session, run_id=run_id, task_id=canonical_task_id)

    assert view.task.task_slug == "solve"
    assert view.task_id == canonical_task_id
    assert view.task.task_id == canonical_task_id
    assert view.is_dynamic is False


def test_graph_repo_node_does_not_reference_definition_tier_models() -> None:
    """PR 2 textual boundary guard: `graph_repo.node`'s source must not
    mention definition-tier symbols. The runtime read path goes through
    run_graph_nodes.task_json only — any subtle import or helper
    delegation to DefinitionRepository would re-open the read path
    PR 11 is closing."""

    import inspect

    source = inspect.getsource(WorkflowGraphRepository.node)
    forbidden = (
        "DefinitionRepository",
        "ExperimentDefinitionTask",
        "task_with_instance",
        "ComponentCatalogService",
    )
    offenders = [symbol for symbol in forbidden if symbol in source]
    assert offenders == [], (
        f"WorkflowGraphRepository.node references definition-tier symbols "
        f"{offenders}; the run-tier read boundary forbids these."
    )


@pytest.mark.asyncio
async def test_add_node_can_write_dynamic_task_json() -> None:
    session = _session()
    run_id = uuid4()
    experiment_id, definition_id, _ = _seed_definition(session, task_slug="parent", payload={})
    _seed_run(
        session,
        experiment_id=experiment_id,
        definition_id=definition_id,
        run_id=run_id,
    )

    repo = WorkflowGraphRepository()
    payload = {
        "_type": "ergon_core.api.benchmark.task:Task",
        "task_slug": "child",
        "description": "child task",
    }
    node_dto = await repo.add_node(
        session,
        run_id,
        task_slug="child",
        instance_key="sample-1",
        description="child task",
        status="pending",
        task_json=payload,
        is_dynamic=True,
        meta=MutationMeta(actor="test", reason="dynamic"),
    )

    row = session.get(RunGraphNode, node_dto.id)
    assert row is not None
    assert row.task_json == payload
    assert row.is_dynamic is True
