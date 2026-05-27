"""Run-tier task snapshot foundation.

Asserts that sample materialization populates `task_json` and `is_dynamic`
correctly, and that `add_node` can accept dynamic task JSON for graph-native
spawns.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from ergon_core.api import Sample
from ergon_core.core.application.runtime.models import MutationMeta
from ergon_core.core.application.runtime.graph_repository import RuntimeGraphRepository
from ergon_core.core.application.samples.materialization import materialize_sample
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.shared.enums import SampleStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord
from pydantic import BaseModel, ConfigDict
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select
from ergon_core.api.benchmark import Task
from ergon_core.test_support.task_factory import TestSandbox, TestWorker


class _EmptyPayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class _SnapshotTask(Task[_EmptyPayload]):
    pass


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _task(*, task_slug: str, payload: dict) -> _SnapshotTask:
    return _SnapshotTask(
        task_slug=task_slug,
        instance_key="sample-1",
        description=f"{task_slug} task",
        task_payload=_EmptyPayload.model_validate(payload),
        worker=TestWorker(name="worker", model="test:none"),
        sandbox=TestSandbox(),
    )


def _seed_run(
    session: Session,
    *,
    sample_id: UUID,
    tasks: list[_SnapshotTask],
) -> None:
    sample_row = SampleRecord(
        id=sample_id,
        benchmark_type="test",
        instance_key="sample-1",
        worker_team_json={},
        status=SampleStatus.EXECUTING,
    )
    session.add(sample_row)
    session.flush()
    materialize_sample(
        session=session,
        sample=Sample.from_tasks(
            name="snapshot-sample",
            sample_key="sample-1",
            environment_name="snapshot-env",
            tasks=tasks,
        ),
        sample_row=sample_row,
    )
    session.commit()


def test_materialize_sample_copies_task_json() -> None:
    session = _session()
    sample_id = uuid4()
    _seed_run(
        session,
        sample_id=sample_id,
        tasks=[_task(task_slug="solve", payload={"problem": "p"})],
    )

    rows = session.exec(select(SampleGraphNode).where(SampleGraphNode.sample_id == sample_id)).all()
    assert rows, "materialize_sample produced no nodes"
    row = rows[0]
    assert row.task_json, "task_json must be populated for static nodes"
    assert row.task_json["task_slug"] == "solve"
    assert row.task_json["task_payload"] == {"problem": "p"}
    assert row.task_json["_type"].endswith(":_SnapshotTask")
    assert row.task_json["worker"]["_type"].endswith(":TestWorker")
    assert row.task_json["sandbox"]["_type"].endswith(":TestSandbox")
    assert row.is_dynamic is False


@pytest.mark.asyncio
async def test_graph_repo_node_inflates_task_from_run_tier() -> None:
    """PR 2 invariant: graph_repo.node reads sample_graph_nodes.task_json
    and returns a typed SampleGraphNodeView with the Task already
    inflated. No definition-tier read; no raw dict in the caller's
    hands."""

    session = _session()
    sample_id = uuid4()
    _seed_run(
        session,
        sample_id=sample_id,
        tasks=[_task(task_slug="solve", payload={"problem": "p"})],
    )

    repo = RuntimeGraphRepository()
    row = session.exec(
        select(SampleGraphNode).where(SampleGraphNode.sample_id == sample_id)
    ).first()
    assert row is not None

    canonical_task_id = row.task_id
    view = await repo.node(session, sample_id=sample_id, task_id=canonical_task_id)

    assert view.task.task_slug == "solve"
    assert view.task_id == canonical_task_id
    assert view.task.task_id == canonical_task_id
    assert view.is_dynamic is False


def test_graph_repo_node_does_not_reference_definition_tier_models() -> None:
    """PR 2 textual boundary guard: `graph_repo.node`'s source must not
    mention definition-tier symbols. The runtime read path goes through
    sample_graph_nodes.task_json only — any subtle import or helper
    delegation to DefinitionRepository would re-open the read path
    PR 11 is closing."""

    import inspect

    source = inspect.getsource(RuntimeGraphRepository.node)
    forbidden = (
        "DefinitionRepository",
        "ExperimentDefinitionTask",
        "task_with_instance",
        "ComponentCatalogService",
    )
    offenders = [symbol for symbol in forbidden if symbol in source]
    assert offenders == [], (
        f"RuntimeGraphRepository.node references definition-tier symbols "
        f"{offenders}; the run-tier read boundary forbids these."
    )


@pytest.mark.asyncio
async def test_add_node_can_write_dynamic_task_json() -> None:
    session = _session()
    sample_id = uuid4()
    _seed_run(
        session,
        sample_id=sample_id,
        tasks=[_task(task_slug="parent", payload={})],
    )

    repo = RuntimeGraphRepository()
    payload = {
        "_type": "ergon_core.api.benchmark.task:Task",
        "task_slug": "child",
        "description": "child task",
    }
    node_dto = await repo.add_node(
        session,
        sample_id,
        task_slug="child",
        instance_key="sample-1",
        description="child task",
        status="pending",
        task_json=payload,
        is_dynamic=True,
        meta=MutationMeta(actor="test", reason="dynamic"),
    )

    row = session.get(SampleGraphNode, (sample_id, node_dto.task_id))
    assert row is not None
    assert row.task_json == payload
    assert row.is_dynamic is True


def test_materialize_sample_isolates_task_ids_for_multiple_samples() -> None:
    session = _session()
    run_a = uuid4()
    run_b = uuid4()
    task = _task(task_slug="solve", payload={"problem": "p"})
    for sample_id in (run_a, run_b):
        _seed_run(session, sample_id=sample_id, tasks=[task])

    task_ids = {
        sample_id: {
            row.task_id
            for row in session.exec(
                select(SampleGraphNode).where(SampleGraphNode.sample_id == sample_id)
            )
        }
        for sample_id in (run_a, run_b)
    }
    assert len(task_ids[run_a]) == len(task_ids[run_b]) == 1
    assert task_ids[run_a].isdisjoint(task_ids[run_b])
