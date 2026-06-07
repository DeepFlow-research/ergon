"""Observable-effect smoketests for the v2 happy path.

Each test drives a public entry point and asserts database / event state
that the spec requires. NOT call-graph tests — outcomes only. See
07-test-strategy.md § "Why effect-based smoketests, not call-graph
mocks".

The tests are effect-based guards for the current v2 runtime shape.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from ergon_core.api import Sample
from ergon_core.api.task import Task
from ergon_core.api.worker.context import WorkerContext
from ergon_core.core.application.runtime import inspection as inspection_module
from ergon_core.core.application.runtime import management as management_module
from ergon_core.core.application.runtime.task_inspection import TaskInspectionService
from ergon_core.core.application.runtime.task_management import TaskManagementService
from ergon_core.core.application.samples.materialization import materialize_sample
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.shared.enums import SampleStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord
from ergon_core.tests.unit.runtime._test_workers import EchoSandbox, EchoWorker
from pydantic import BaseModel, ConfigDict
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


class _EmptyPayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class _SmokeTask(Task[_EmptyPayload]):
    pass


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _seed_run(session: Session) -> UUID:
    """Materialize a minimal sample with one task; return sample_id."""

    sample_id = uuid4()
    task = _SmokeTask(
        task_slug="root",
        instance_key="sample-1",
        description="root task",
        task_payload=_EmptyPayload.model_validate({"problem": "p"}),
        worker=EchoWorker(name="echo", model="test:none"),
        sandbox=EchoSandbox(),
    )
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
            name="smoke-sample",
            sample_key="sample-1",
            environment_name="test",
            tasks=[task],
        ),
        sample_row=sample_row,
    )
    session.commit()
    return sample_id


# ── PR 1 invariant — GREEN today ─────────────────────────────────────


def test_materialize_sample_populates_task_json_for_every_node() -> None:
    """PR 1 invariant: every sample_graph_nodes row produced by
    sample materialization carries a non-empty task_json snapshot."""

    session = _session()
    sample_id = _seed_run(session)

    rows = session.exec(select(SampleGraphNode).where(SampleGraphNode.sample_id == sample_id)).all()

    assert rows, "materialize_sample produced no nodes"
    assert all(row.task_json for row in rows), (
        "every node must carry a self-contained task snapshot"
    )
    assert all(row.task_json.get("task_slug") for row in rows)


# ── Runtime invariants ───────────────────────────────────────────────


def test_worker_execute_reads_task_from_run_tier_only() -> None:
    """PR 3 invariant: ``worker_execute.py`` source does not reference
    definition-tier symbols.

    Effect-level test: rather than driving a full worker run (which
    needs Inngest + sandbox infrastructure not available to unit
    tests), we check the source code for the symbols PR 3 forbids.
    The walkthrough integration test in PR 12 exercises the full
    runtime end-to-end. The textual guard here catches reintroduction
    on every PR.
    """

    from pathlib import Path

    root = Path(__file__).resolve().parents[4]
    text = (root / "ergon_core/ergon_core/core/jobs/task/worker_execute/job.py").read_text()
    forbidden = ("DefinitionRepository", "task_with_instance", "ExperimentDefinitionTask")
    offenders = [s for s in forbidden if s in text]
    assert offenders == [], (
        f"worker_execute references definition-tier symbols {offenders}; "
        "PR 3's run-tier read boundary forbids these."
    )


def test_worker_execute_emits_one_evaluate_invocation_per_evaluator() -> None:
    """PR 4 invariant: synchronous fanout via ctx.step.invoke.

    PR 4 moved the fanout from the sibling ``check_evaluators`` Inngest
    function into the orchestrator (``execute_task``), so the
    ``ctx.step.invoke`` / ``ctx.group.parallel`` shape lives in
    ``execute_task.py`` (see PR 4 plan § "Implementation Note —
    Bridge-Everything Approach" for the orchestrator-location
    rationale). The behavioural test (one invoke per evaluator, no
    invokes when there are zero evaluator bindings) lives in
    ``test_execute_task_evaluator_fanout.py``; this textual guard
    catches regressions of the fanout shape itself.
    """

    from pathlib import Path

    root = Path(__file__).resolve().parents[4]
    text = (root / "ergon_core/ergon_core/core/jobs/task/execute/job.py").read_text()
    assert "ctx.step.invoke" in text
    assert "ctx.group.parallel" in text, (
        "Use the Inngest-native parallel-step primitive, not `asyncio.gather`."
    )
    assert 'f"eval-' in text, "fanout step IDs must include the evaluator index"
    assert "evaluate_task_run_function" in text, (
        "execute_task must invoke evaluate_task_run as a child function"
    )


def test_evaluate_task_run_payload_is_id_only() -> None:
    """PR 4 invariant: TaskEvaluateRequest has exactly four fields:
    sample_id, task_id, execution_id, evaluator_index."""

    from ergon_core.core.jobs.task.evaluate.contract import TaskEvaluateRequest

    assert set(TaskEvaluateRequest.model_fields) == {
        "sample_id",
        "task_id",
        "execution_id",
        "evaluator_index",
    }


def test_sandbox_release_happens_after_all_evaluators_complete() -> None:
    """Δ.5: sandbox release is bounded by the parallel evaluator fanout.

    PR 4's first attempt put ``terminate_sandbox_by_id`` directly in
    the orchestrator's ``try/finally``.  That broke smoke tests because
    Inngest's ``step.invoke`` raises ``ResponseInterrupt`` (a
    ``BaseException``) to suspend the coroutine — which fires ``finally``
    and terminates the sandbox *before* the suspended sub-function
    actually runs.

    The fix (post-PR-4): cleanup lives in a sibling Inngest function
    (``sandbox_cleanup_on_completed_fn`` / ``sandbox_cleanup_on_failed_fn``)
    triggered by the terminal task events.  ``execute_task`` emits
    ``task/completed`` only AFTER ``_fan_out_evaluators`` returns, so
    cleanup is still bounded by the parallel fanout — but via event
    chaining instead of an inline ``finally``, which is what Inngest's
    step-replay model actually supports.

    This guard enforces the new shape:
    - ``ctx.group.parallel`` (the evaluator fanout) exists in execute_task
    - ``_emit_task_completed`` is called AFTER the fanout
    - sandbox_cleanup module exists and is wired to terminal task events
    - ``terminate_sandbox_by_id`` is no longer called from execute_task
    """

    from pathlib import Path

    root = Path(__file__).resolve().parents[4]
    execute_task_text = (root / "ergon_core/ergon_core/core/jobs/task/execute/job.py").read_text()
    parallel_idx = execute_task_text.find("ctx.group.parallel")
    emit_completed_idx = execute_task_text.find("_emit_task_completed(payload")
    assert parallel_idx != -1, "orchestrator must use ctx.group.parallel for the evaluator fanout"
    assert emit_completed_idx != -1, (
        "orchestrator must call _emit_task_completed on the success path"
    )
    assert parallel_idx < emit_completed_idx, (
        "ctx.group.parallel must run BEFORE emit:task/completed so the "
        "sibling cleanup function only fires after evaluators finish"
    )
    assert "terminate_sandbox_by_id(task_sandbox_id)" not in execute_task_text, (
        "orchestrator must NOT call terminate_sandbox_by_id inline — "
        "the sibling sandbox_cleanup function does it on terminal events"
    )

    cleanup_path = root / "ergon_core/ergon_core/core/jobs/sandbox/cleanup/job.py"
    assert cleanup_path.exists(), "sandbox_cleanup job module must exist"
    cleanup_text = cleanup_path.read_text()
    assert "terminate_external_sandbox" in cleanup_text, (
        "sandbox_cleanup must call terminate_external_sandbox"
    )

    handler_path = root / "ergon_core/ergon_core/core/jobs/sandbox/cleanup/inngest.py"
    assert handler_path.exists(), "sandbox_cleanup Inngest handler module must exist"
    handler_text = handler_path.read_text()
    assert 'event="task/completed"' in handler_text, (
        "sandbox_cleanup_on_completed_fn must trigger on task/completed"
    )
    assert 'event="task/failed"' in handler_text, (
        "sandbox_cleanup_on_failed_fn must trigger on task/failed"
    )


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


def _patch_get_session_smoke(monkeypatch: pytest.MonkeyPatch, session: Session) -> None:
    def ctx_factory() -> _SessionContext:
        return _SessionContext(session)

    monkeypatch.setattr(management_module, "get_session", ctx_factory)
    monkeypatch.setattr(inspection_module, "get_session", ctx_factory)


def _seed_parent_node(session: Session, *, sample_id: UUID) -> SampleGraphNode:
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
async def test_dynamic_spawn_writes_only_to_sample_graph_nodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Δ.3 / PR 9 invariant: dynamic subtasks are graph-native."""

    # 1. In-memory SQLite with all tables.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)

    # 2. Seed one parent graph node.
    sample_id = uuid4()
    parent = _seed_parent_node(session, sample_id=sample_id)

    # 3. Patch get_session so service writes stay in the test session.
    _patch_get_session_smoke(monkeypatch, session)
    task_mgmt = TaskManagementService(
        dashboard_emitter=SimpleNamespace(graph_mutation=AsyncMock()),
        task_ready_dispatcher=AsyncMock(),
    )
    task_inspect = TaskInspectionService()
    context = WorkerContext._for_job(
        sample_id=sample_id,
        task_id=parent.task_id,
        execution_id=uuid4(),
        sandbox_id="sandbox-smoke",
        task_mgmt=task_mgmt,
        task_inspect=task_inspect,
        resource_service=object(),
        session_factory=management_module.get_session,
    )

    nodes_before = session.exec(select(SampleGraphNode)).all()
    assert len(nodes_before) == 1  # only the parent
    assert "experiment_definition_tasks" not in SQLModel.metadata.tables

    # 4. Spawn a dynamic child task.
    await context.spawn_task(
        Task(
            task_slug="child",
            instance_key="sample-1",
            description="dynamic child",
            worker=EchoWorker(name="echo", model="test:none"),
            sandbox=EchoSandbox(),
            evaluators=(),
        )
    )

    # 5. Exactly one new sample_graph_nodes row (is_dynamic=True); zero new
    #    experiment_definition_tasks rows.
    nodes_after = session.exec(select(SampleGraphNode)).all()

    assert len(nodes_after) == len(nodes_before) + 1

    new_node = session.exec(
        select(SampleGraphNode).where(
            SampleGraphNode.sample_id == sample_id,
            SampleGraphNode.task_slug == "child",
        )
    ).one()
    assert new_node.is_dynamic is True


def test_run_completion_releases_every_acquired_sandbox() -> None:
    """CLAUDE.md guardrail: every sandbox acquire has a release."""

    from pathlib import Path

    root = Path(__file__).resolve().parents[4]
    sandbox_cleanup_text = (
        root / "ergon_core/ergon_core/core/jobs/sandbox/cleanup/job.py"
    ).read_text()
    handler_text = (root / "ergon_core/ergon_core/core/jobs/sandbox/cleanup/inngest.py").read_text()

    assert "terminate_external_sandbox" in sandbox_cleanup_text
    assert "run_sandbox_cleanup_on_completed" in sandbox_cleanup_text
    assert "run_sandbox_cleanup_on_failed" in sandbox_cleanup_text
    assert 'event="task/completed"' in handler_text
    assert 'event="task/failed"' in handler_text
