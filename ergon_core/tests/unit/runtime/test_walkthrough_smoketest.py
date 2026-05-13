"""Observable-effect smoketests for the v2 happy path.

Each test drives a public entry point and asserts database / event state
that the spec requires. NOT call-graph tests — outcomes only. See
07-test-strategy.md § "Why effect-based smoketests, not call-graph
mocks".

Tests for invariants that have not landed are xfail(strict=True) with
the landing PR in the reason. Removing the decorator is the landing-PR
signal.

PR 1 lands one passing case
(test_prepare_run_populates_task_json_for_every_node); the rest are
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


def _seed_run(session: Session) -> tuple[UUID, UUID]:
    """Insert a minimal experiment/definition/run with one task; return
    (run_id, definition_id)."""

    experiment_id = uuid4()
    definition_id = uuid4()
    instance_id = uuid4()
    task_id = uuid4()
    run_id = uuid4()
    session.add_all(
        [
            ExperimentRecord(
                id=experiment_id,
                name="smoke",
                benchmark_type="test",
                sample_count=1,
            ),
            ExperimentDefinition(id=definition_id, benchmark_type="test", metadata_json={}),
            ExperimentDefinitionInstance(
                id=instance_id,
                experiment_definition_id=definition_id,
                instance_key="sample-1",
            ),
            ExperimentDefinitionTask(
                id=task_id,
                experiment_definition_id=definition_id,
                instance_id=instance_id,
                task_slug="root",
                description="root task",
                task_payload_json={"problem": "p"},
            ),
            RunRecord(
                id=run_id,
                experiment_id=experiment_id,
                workflow_definition_id=definition_id,
                benchmark_type="test",
                instance_key="sample-1",
                worker_team_json={},
                status=RunStatus.EXECUTING,
            ),
        ]
    )
    session.commit()
    return run_id, definition_id


# ── PR 1 invariant — GREEN today ─────────────────────────────────────


def test_prepare_run_populates_task_json_for_every_node() -> None:
    """PR 1 invariant: every run_graph_nodes row produced by
    initialize_from_definition carries a non-empty task_json
    snapshot."""

    session = _session()
    run_id, definition_id = _seed_run(session)

    repo = WorkflowGraphRepository()
    repo.initialize_from_definition(
        session,
        run_id=run_id,
        definition_id=definition_id,
        initial_node_status="pending",
        initial_edge_status="pending",
        task_payload_model=_EmptyPayload,
        meta=MutationMeta(actor="test", reason="smoke"),
    )

    rows = session.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).all()

    assert rows, "prepare_run produced no nodes"
    assert all(row.task_json for row in rows), (
        "every node must carry a self-contained task snapshot"
    )
    assert all(row.task_json.get("task_slug") for row in rows)


# ── Future-PR invariants — xfailed pending implementation ────────────


@pytest.mark.xfail(
    reason="PR 7: persist_definition collapses ExperimentRecord onto definitions",
    strict=True,
)
def test_persist_definition_writes_only_intended_tables() -> None:
    """PR 7 invariant: persist_definition writes experiment_definitions
    plus experiment_definition_tasks. No write to ExperimentRecord, no
    write to saved_specs."""

    pytest.fail("requires PR 7's persistence collapse + helper rewrite")


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
    text = (root / "ergon_core/ergon_core/core/application/jobs/worker_execute.py").read_text()
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
    text = (root / "ergon_core/ergon_core/core/application/jobs/execute_task.py").read_text()
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
    run_id, task_id, execution_id, evaluator_index."""

    from ergon_core.core.application.jobs.models import TaskEvaluateRequest

    assert set(TaskEvaluateRequest.model_fields) == {
        "run_id",
        "task_id",
        "execution_id",
        "evaluator_index",
    }


def test_sandbox_release_happens_after_all_evaluators_complete() -> None:
    """Δ.5: orchestrator's try/finally bounds sandbox lifetime through
    the parallel fanout.

    PR 4 lifts sandbox termination from the sibling
    ``check_evaluators`` job into the orchestrator's ``finally``. The
    textual guard ensures the parallel fanout (`ctx.group.parallel`)
    is upstream of ``terminate_sandbox_by_id`` and that the
    termination only happens inside a ``finally`` block — i.e. the
    only termination path is bounded by the parallel fan-out.
    """

    from pathlib import Path

    root = Path(__file__).resolve().parents[4]
    text = (root / "ergon_core/ergon_core/core/application/jobs/execute_task.py").read_text()
    finally_idx = text.find("finally:")
    terminate_idx = text.find("terminate_sandbox_by_id(task_sandbox_id)")
    parallel_idx = text.find("ctx.group.parallel")
    assert finally_idx != -1, "orchestrator must wrap sandbox release in try/finally"
    assert terminate_idx != -1, "orchestrator must terminate sandbox in its finally"
    assert finally_idx < terminate_idx, (
        "terminate_sandbox_by_id(task_sandbox_id) must live inside the finally block"
    )
    assert parallel_idx != -1 and parallel_idx < finally_idx, (
        "ctx.group.parallel over evaluator invokes must run before the finally"
    )


@pytest.mark.xfail(
    reason="PR 9: dynamic subtasks write only to run_graph_nodes",
    strict=True,
)
def test_dynamic_spawn_writes_only_to_run_graph_nodes() -> None:
    """Δ.3 / PR 9 invariant: dynamic subtasks are graph-native."""

    pytest.fail("requires PR 9's graph-native dynamic spawn")


@pytest.mark.xfail(
    reason="PR 11: full v2 lifecycle — every acquire has a release",
    strict=True,
)
def test_run_completion_releases_every_acquired_sandbox() -> None:
    """CLAUDE.md guardrail: every sandbox acquire has a release."""

    pytest.fail("requires the full v2 lifecycle shape")
