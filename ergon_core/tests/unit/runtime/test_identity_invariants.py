"""Runtime identity-flow invariants.

task_id is born during sample materialization and flows unchanged through
SampleGraphNode, typed WAL, and inflated runtime Task instances. (sample_id,
task_id) is the canonical row key. execution_id is the per-attempt id. Sandbox
identity is preserved across the worker → evaluate Inngest boundary.

These are observable-effect tests, not call-graph tests.

PR 1 lands one passing case
(test_task_id_is_preserved_from_definition_to_run_tier); the rest are
xfailed until their landing PRs.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from ergon_core.api import Sample
from ergon_core.api.benchmark.task import Task
from ergon_core.api.worker.context import WorkerContext
from ergon_core.api.worker.results import SpawnedTaskHandle
from ergon_core.core.application.runtime.graph_repository import RuntimeGraphRepository
from ergon_core.core.application.runtime import inspection as inspection_module
from ergon_core.core.application.runtime import management as management_module
from ergon_core.core.application.runtime.task_inspection import TaskInspectionService
from ergon_core.core.application.runtime.task_management import TaskManagementService
from ergon_core.core.application.samples.materialization import materialize_sample
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.samples.models import SampleTaskEventRow
from ergon_core.core.persistence.shared.enums import SampleStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord
from ergon_core.tests.unit.runtime._test_workers import EchoSandbox, EchoWorker
from pydantic import BaseModel, ConfigDict
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


class _EmptyPayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class _IdentityTask(Task[_EmptyPayload]):
    pass


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _seed_materialized_sample(session: Session) -> tuple[UUID, set[UUID]]:
    """Materialize a sample with two tasks; return (sample_id, task_ids)."""

    sample_id = uuid4()
    sample_row = SampleRecord(
        id=sample_id,
        benchmark_type="test",
        instance_key="sample-1",
        worker_team_json={},
        status=SampleStatus.EXECUTING,
    )
    session.add(sample_row)
    session.flush()
    sample = Sample.from_tasks(
        name="identity-sample",
        sample_key="sample-1",
        environment_name="identity-env",
        tasks=[
            _IdentityTask(
                task_slug=f"task-{i}",
                instance_key="sample-1",
                description=f"task {i}",
                task_payload=_EmptyPayload(),
                worker=EchoWorker(name="echo", model="test:none"),
                sandbox=EchoSandbox(),
            )
            for i in range(2)
        ],
    )
    materialize_sample(session=session, sample=sample, sample_row=sample_row)
    session.commit()
    task_ids = {
        row.task_id
        for row in session.exec(
            select(SampleGraphNode).where(SampleGraphNode.sample_id == sample_id)
        )
    }
    return sample_id, task_ids


# ── PR 1 invariant — GREEN today ─────────────────────────────────────


def test_task_id_is_preserved_from_materialized_graph_to_typed_wal() -> None:
    """The same UUID flows through sample_graph_nodes and typed task events.

    The runtime identity lives in ``task_id``.
    """

    session = _session()
    sample_id, graph_task_ids = _seed_materialized_sample(session)

    rows = session.exec(select(SampleGraphNode).where(SampleGraphNode.sample_id == sample_id)).all()
    assert "task_id" in SampleGraphNode.model_fields
    assert "id" not in SampleGraphNode.model_fields
    seen = {row.task_id for row in rows}
    assert seen == graph_task_ids

    wal_task_ids = {
        event.task_id
        for event in session.exec(
            select(SampleTaskEventRow)
            .where(SampleTaskEventRow.sample_id == sample_id)
            .where(SampleTaskEventRow.event_type == "task.added")
        )
    }
    assert wal_task_ids == graph_task_ids


# ── Future-PR invariants — xfailed pending implementation ────────────


@pytest.mark.asyncio
async def test_task_id_propagates_into_runtime_task_instance() -> None:
    """PR 2 invariant: Task.from_definition binds _task_id; reading
    `task.task_id` on the inflated instance returns the same UUID the
    materialized graph row has."""

    session = _session()
    sample_id, graph_task_ids = _seed_materialized_sample(session)

    repo = RuntimeGraphRepository()
    nodes = session.exec(
        select(SampleGraphNode).where(SampleGraphNode.sample_id == sample_id)
    ).all()
    for row in nodes:
        canonical_id = row.task_id
        view = await repo.node(session, sample_id=sample_id, task_id=canonical_id)
        assert view.task_id == canonical_id
        assert view.task.task_id == canonical_id
    # And the inflated task ids match the original definition task ids
    seen = set()
    for row in nodes:
        canonical_id = row.task_id
        view = await repo.node(session, sample_id=sample_id, task_id=canonical_id)
        seen.add(view.task.task_id)
    assert seen == graph_task_ids


def test_sandbox_identity_is_preserved_across_worker_to_evaluate_boundary() -> None:
    """Δ.5: the sandbox acquired in worker_execute is the one each
    evaluate_task_run invocation attaches to via sandbox_id.

    PR 5 keeps this concrete behind the public task execution facade:
    ``worker_execute`` stamps the live ``sandbox_id`` onto the execution
    row, and ``evaluate_task_run`` reads ``execution.sandbox_id`` and
    passes it to ``load_task_view(..., sandbox_id=...)`` to reattach. The
    ``sandbox_id`` field on ``SampleTaskAttempt`` is the carrier; the
    structural guard checks both halves of the contract.
    """

    from pathlib import Path

    from ergon_core.core.application.runtime.task_execution_repository import (
        TaskExecutionRepository,
    )
    from ergon_core.core.persistence.telemetry.models import SampleTaskAttempt

    # Carrier: the execution row owns the sandbox_id.
    assert "sandbox_id" in SampleTaskAttempt.model_fields
    # Internal writer still owns the column mutation; jobs reach it through
    # TaskExecutionService.attach_sandbox_to_execution.
    assert hasattr(TaskExecutionRepository, "set_sandbox_id")

    root = Path(__file__).resolve().parents[4]
    worker_text = (root / "ergon_core/ergon_core/core/jobs/task/worker_execute/job.py").read_text()
    eval_text = (root / "ergon_core/ergon_core/core/jobs/task/evaluate/job.py").read_text()

    # Producer side: worker_execute stamps sandbox_id through the facade.
    assert "attach_sandbox_to_execution(" in worker_text
    assert "sandbox_id=payload.sandbox_id" in worker_text

    # Consumer side: evaluate_task_run reads sandbox_id from the
    # execution row and forwards it to the run-tier loader.
    assert "load_task_view(" in eval_text
    assert "execution.sandbox_id" in eval_text
    assert "sandbox_id=execution.sandbox_id" in eval_text


def test_execution_id_is_unique_per_attempt_and_shared_across_evaluators() -> None:
    """Two evaluator invocations for the same execution share
    execution_id; a retry mints a new one.

    PR 4 makes execution_id the join key linking
    ``SampleTaskAttempt`` ⇄ ``TaskExecutionService`` ⇄ each
    ``TaskEvaluateRequest`` invocation. The structural guard checks
    that (a) ``TaskEvaluateRequest`` carries ``execution_id``, (b) the
    orchestrator's fanout reuses ``prepared.execution_id`` for every
    invoke (one execution_id, many evaluator_indices), and (c) a fresh
    attempt mints a new execution_id via the existing
    ``next_attempt_for_node`` path.
    """

    import inspect
    from pathlib import Path

    from ergon_core.core.jobs.task.evaluate.contract import TaskEvaluateRequest
    from ergon_core.core.application.runtime.task_execution_repository import (
        TaskExecutionRepository,
    )

    # (a) execution_id is on the payload.
    assert "execution_id" in TaskEvaluateRequest.model_fields

    # (b) the fanout reuses the same execution_id across evaluator_indices.
    root = Path(__file__).resolve().parents[4]
    orchestrator = (root / "ergon_core/ergon_core/core/jobs/task/execute/job.py").read_text()
    fanout_start = orchestrator.find("def _fan_out_evaluators")
    assert fanout_start != -1, "fanout helper must exist on the orchestrator"
    # Slice until the next top-level `def `; the docstring length isn't
    # stable across edits so a fixed-width slice would miss the body.
    next_def = orchestrator.find("\ndef ", fanout_start + 1)
    fanout_body = (
        orchestrator[fanout_start:next_def] if next_def != -1 else orchestrator[fanout_start:]
    )
    assert "execution_id=prepared.execution_id" in fanout_body, (
        "every per-evaluator invoke must share prepared.execution_id"
    )
    assert "evaluator_index=i" in fanout_body, (
        "evaluator_index must vary across the parallel fanout (one execution, many indices)"
    )

    # (c) a retry mints a new execution_id — the attempt counter on
    # TaskExecutionRepository is the canonical source.
    assert "next_attempt_for_node" in inspect.getsource(TaskExecutionRepository)


class _SessionContext:
    """Context-manager shim that wraps a pre-existing Session.

    Used so service code calling ``get_session()`` reuses the test's
    in-memory SQLite session rather than opening a new connection.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *args: object) -> None:
        return None


def _patch_get_session_identity(monkeypatch: pytest.MonkeyPatch, session: Session) -> None:
    def ctx_factory() -> _SessionContext:
        return _SessionContext(session)

    monkeypatch.setattr(management_module, "get_session", ctx_factory)
    monkeypatch.setattr(inspection_module, "get_session", ctx_factory)


def _seed_identity_parent(session: Session, *, sample_id: UUID) -> SampleGraphNode:
    session.add(
        SampleRecord(
            id=sample_id,
            benchmark_type="test",
            instance_key="sample-1",
            worker_team_json={},
            status=SampleStatus.EXECUTING,
        )
    )
    node = SampleGraphNode(
        sample_id=sample_id,
        instance_key="sample-1",
        task_slug="parent",
        description="parent task",
        status="RUNNING",
        is_dynamic=False,
        parent_task_id=None,
        level=0,
    )
    session.add(node)
    session.commit()
    return node


@pytest.mark.asyncio
async def test_dynamic_task_id_has_no_definition_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Δ.3: dynamic spawn writes only to sample_graph_nodes."""

    # 1. In-memory SQLite with all tables.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)

    sample_id = uuid4()
    parent = _seed_identity_parent(session, sample_id=sample_id)

    _patch_get_session_identity(monkeypatch, session)
    task_mgmt = TaskManagementService(
        dashboard_emitter=SimpleNamespace(graph_mutation=AsyncMock()),
        task_ready_dispatcher=AsyncMock(),
    )
    task_inspect = TaskInspectionService()
    context = WorkerContext._for_job(
        sample_id=sample_id,
        task_id=parent.task_id,
        execution_id=uuid4(),
        sandbox_id="sandbox-identity",
        task_mgmt=task_mgmt,
        task_inspect=task_inspect,
        resource_service=object(),
        session_factory=management_module.get_session,
    )

    # Spawn a dynamic child task.
    handle = await context.spawn_task(
        _IdentityTask(
            task_slug="child",
            instance_key="sample-1",
            description="dynamic child",
            worker=EchoWorker(name="echo", model="test:none"),
            sandbox=EchoSandbox(),
            evaluators=(),
        )
    )

    assert isinstance(handle, SpawnedTaskHandle)

    # 2. Dynamic task creation must not depend on retired definition tables.
    assert "experiment_definition_tasks" not in SQLModel.metadata.tables

    # 3. The returned task_id appears as the task_id of exactly one sample_graph_nodes row.
    node_count = len(
        session.exec(select(SampleGraphNode).where(SampleGraphNode.task_id == handle.task_id)).all()
    )
    assert node_count == 1

    child_context = WorkerContext._for_job(
        sample_id=sample_id,
        task_id=handle.task_id,
        execution_id=uuid4(),
        sandbox_id="sandbox-child",
        task_mgmt=task_mgmt,
        task_inspect=task_inspect,
        resource_service=object(),
        session_factory=management_module.get_session,
    )
    assert child_context.task_id == handle.task_id
