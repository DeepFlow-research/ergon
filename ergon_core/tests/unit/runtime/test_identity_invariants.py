"""Identity-flow invariants from 02-persistence-layer.md §2.

task_id is born once and flows unchanged. (run_id, task_id) is the
canonical row key. execution_id is the per-attempt id. Sandbox identity
is preserved across the worker → evaluate Inngest boundary.

These are observable-effect tests, not call-graph tests.

PR 1 lands one passing case
(test_task_id_is_preserved_from_definition_to_run_tier); the rest are
xfailed until their landing PRs.
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
    ExperimentRecord,
    RunRecord,
)
from pydantic import BaseModel
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


class _EmptyPayload(BaseModel):
    pass


def _session() -> Session:
    _ = ExperimentRecord
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _seed_definition(session: Session) -> tuple[UUID, UUID, set[UUID]]:
    """Insert a definition with two tasks; return (definition_id, run_id,
    set_of_definition_task_ids)."""

    experiment_id = uuid4()
    definition_id = uuid4()
    instance_id = uuid4()
    task_ids = {uuid4(), uuid4()}
    run_id = uuid4()
    session.add_all(
        [
            ExperimentRecord(
                id=experiment_id,
                name="identity",
                benchmark_type="test",
                sample_count=1,
            ),
            ExperimentDefinition(id=definition_id, benchmark_type="test", metadata_json={}),
            ExperimentDefinitionInstance(
                id=instance_id,
                experiment_definition_id=definition_id,
                instance_key="sample-1",
            ),
        ]
    )
    for i, task_id in enumerate(task_ids):
        session.add(
            ExperimentDefinitionTask(
                id=task_id,
                experiment_definition_id=definition_id,
                instance_id=instance_id,
                task_slug=f"task-{i}",
                description=f"task {i}",
                task_payload_json={},
            )
        )
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
    return definition_id, run_id, task_ids


# ── PR 1 invariant — GREEN today ─────────────────────────────────────


def test_task_id_is_preserved_from_definition_to_run_tier() -> None:
    """PR 1 invariant: the same UUID flows from
    experiment_definition_tasks → run_graph_nodes.

    During the transition, run-tier identity lives in either
    ``definition_task_id`` (copied from definition) or ``id`` (run-tier
    minted). PR 11 collapses to ``task_id``.
    """

    session = _session()
    definition_id, run_id, defn_task_ids = _seed_definition(session)

    repo = WorkflowGraphRepository()
    repo.initialize_from_definition(
        session,
        run_id=run_id,
        definition_id=definition_id,
        initial_node_status="pending",
        initial_edge_status="pending",
        task_payload_model=_EmptyPayload,
        meta=MutationMeta(actor="test", reason="identity"),
    )

    rows = session.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).all()
    # Every definition_task_id should appear on exactly one run-graph
    # row.
    seen = {row.definition_task_id for row in rows}
    assert seen == defn_task_ids, (
        f"task_id did not survive prepare: definition={defn_task_ids}, run-tier={seen}"
    )


# ── Future-PR invariants — xfailed pending implementation ────────────


@pytest.mark.asyncio
async def test_task_id_propagates_into_runtime_task_instance() -> None:
    """PR 2 invariant: Task.from_definition binds _task_id; reading
    `task.task_id` on the inflated instance returns the same UUID the
    definition row had."""

    session = _session()
    definition_id, run_id, defn_task_ids = _seed_definition(session)

    repo = WorkflowGraphRepository()
    repo.initialize_from_definition(
        session,
        run_id=run_id,
        definition_id=definition_id,
        initial_node_status="pending",
        initial_edge_status="pending",
        task_payload_model=_EmptyPayload,
        meta=MutationMeta(actor="test", reason="identity"),
    )

    nodes = session.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).all()
    for row in nodes:
        canonical_id = row.definition_task_id or row.id
        view = await repo.node(session, run_id=run_id, task_id=canonical_id)
        assert view.task_id == canonical_id
        assert view.task.task_id == canonical_id
    # And the inflated task ids match the original definition task ids
    seen = set()
    for row in nodes:
        canonical_id = row.definition_task_id or row.id
        view = await repo.node(session, run_id=run_id, task_id=canonical_id)
        seen.add(view.task.task_id)
    assert seen == defn_task_ids


@pytest.mark.xfail(
    reason="PR 4: orchestrator stamps sandbox_id on run_task_executions",
    strict=True,
)
def test_sandbox_identity_is_preserved_across_worker_to_evaluate_boundary() -> None:
    """Δ.5: the sandbox acquired in worker_execute is the one each
    evaluate_task_run invocation attaches to via sandbox_id."""

    pytest.fail("requires PR 4's persisted sandbox_id contract")


@pytest.mark.xfail(
    reason="PR 4: execution_id flows through TaskEvaluateRequest payload",
    strict=True,
)
def test_execution_id_is_unique_per_attempt_and_shared_across_evaluators() -> None:
    """Two evaluator invocations for the same execution share
    execution_id; a retry mints a new one."""

    pytest.fail("requires PR 4's TaskEvaluateRequest")


@pytest.mark.xfail(
    reason="PR 9: dynamic task_id is fresh uuid4 with no definition row",
    strict=True,
)
def test_dynamic_task_id_has_no_definition_row() -> None:
    """Δ.3: dynamic spawn writes only to run_graph_nodes."""

    pytest.fail("requires PR 9's graph-native spawn")
