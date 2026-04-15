"""E2E integration test for the researchrubrics pipeline (offline, no real E2B).

Exercises the full stack with all externals stubbed:
  - FakeAsyncSandbox with in-memory files (no real E2B)
  - Stub worker writes a canned report
  - Publisher syncs to blob store
  - StubReportExistsCriterion evaluates the report
  - LLM-judge criterion stubbed to return deterministic verdict

Verifies that RunResource rows exist, the criterion ran, and the run
completes successfully.
"""

import asyncio
import hashlib
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from sqlmodel import Session, select

from ergon_builtins.benchmarks.researchrubrics.smoke import (
    ResearchRubricsSmokeTestBenchmark,
)
from ergon_builtins.benchmarks.researchrubrics.smoke_rubric import (
    ResearchRubricsSmokeRubric,
)
from ergon_builtins.evaluators.criteria.stub_report_exists import (
    StubReportExistsCriterion,
)
from ergon_builtins.workers.research_rubrics.stub_worker import (
    STUB_REPORT_CONTENT,
)
from ergon_core.api import Experiment
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.generation import GenerationTurn, TextPart
from ergon_core.api.results import CriterionResult, WorkerOutput
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.worker_context import WorkerContext
from ergon_core.core.persistence.queries import queries
from ergon_core.core.persistence.shared.db import ensure_db, get_session
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunResourceKind,
    RunTaskEvaluation,
    RunTaskExecution,
)
from ergon_core.core.providers.sandbox.resource_publisher import (
    SandboxResourcePublisher,
)
from ergon_core.core.runtime.services.run_service import create_run
from ergon_core.core.runtime.services.orchestration_dto import (
    FinalizeTaskExecutionCommand,
    FinalizeWorkflowCommand,
    InitializeWorkflowCommand,
    PrepareTaskExecutionCommand,
    PropagateTaskCompletionCommand,
)
from ergon_core.core.runtime.services.task_execution_service import (
    TaskExecutionService,
)
from ergon_core.core.runtime.services.task_propagation_service import (
    TaskPropagationService,
)
from ergon_core.core.runtime.services.workflow_finalization_service import (
    WorkflowFinalizationService,
)
from ergon_core.core.runtime.services.workflow_initialization_service import (
    WorkflowInitializationService,
)


# ---------------------------------------------------------------------------
# Fake sandbox stubs (mirrors tests/state/test_sandbox_resource_publisher.py)
# ---------------------------------------------------------------------------


class _FakeEntry:
    def __init__(self, *, name: str) -> None:
        self.name = name


class _FakeSandboxFiles:
    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}

    def put(self, path: str, content: bytes) -> None:
        self._files[path] = content

    async def list(self, path: str) -> list[_FakeEntry]:
        prefix = path if path.endswith("/") else path + "/"
        entries: list[_FakeEntry] = []
        seen: set[str] = set()
        for key in self._files:
            if key.startswith(prefix):
                remainder = key[len(prefix) :]
                if "/" not in remainder and remainder not in seen:
                    entries.append(_FakeEntry(name=remainder))
                    seen.add(remainder)
        if not entries:
            raise FileNotFoundError(path)
        return entries

    async def read(self, path: str, *, request_timeout: int = 30) -> bytes:
        if path not in self._files:
            raise FileNotFoundError(path)
        return self._files[path]

    async def write(self, path: str, content: str | bytes) -> None:
        if isinstance(content, str):
            content = content.encode("utf-8")
        self._files[path] = content


class _FakeCommands:
    async def run(self, cmd: str, **kwargs: object) -> object:  # noqa: ARG002
        class _Result:
            exit_code = 0
            stdout = ""
            stderr = ""

        return _Result()


class _FakeSandbox:
    sandbox_id = "fake-sandbox-e2e"

    def __init__(self) -> None:
        self.files = _FakeSandboxFiles()
        self.commands = _FakeCommands()


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_researchrubrics_e2e_offline(tmp_path: Path) -> None:
    """Golden-path E2E: smoke benchmark -> stub worker -> publisher -> criterion."""
    ensure_db()

    # ── Construct ──────────────────────────────────────────────────
    benchmark = ResearchRubricsSmokeTestBenchmark(limit=1)
    rubric = ResearchRubricsSmokeRubric()

    # We use the StubWorker directly (bypassing registry resolution)
    # because we need to inject the fake sandbox.
    from ergon_builtins.workers.baselines.stub_worker import StubWorker

    worker = StubWorker(name="researchrubrics-stub", model="openai:gpt-4o")

    experiment = Experiment.from_single_worker(
        benchmark=benchmark,
        worker=worker,
        evaluators={"default": rubric},
    )
    experiment.validate()
    persisted = experiment.persist()

    # ── Create Run + Initialize ────────────────────────────────────
    run = create_run(persisted)
    init_svc = WorkflowInitializationService()
    initialized = init_svc.initialize(
        InitializeWorkflowCommand(
            run_id=run.id,
            definition_id=persisted.definition_id,
        )
    )
    assert initialized.total_tasks >= 1

    # ── Execute Tasks (with fake sandbox + publisher) ──────────────
    exec_svc = TaskExecutionService()
    completed_tasks = []

    fake_sandbox = _FakeSandbox()
    blob_root = tmp_path / "blobs"
    blob_root.mkdir()

    for task_desc in initialized.initial_ready_tasks:
        prepared = exec_svc.prepare(
            PrepareTaskExecutionCommand(
                run_id=run.id,
                definition_id=persisted.definition_id,
                task_id=task_desc.task_id,
            )
        )

        # Write the stub report to the fake sandbox.
        report_content = STUB_REPORT_CONTENT.encode("utf-8")
        asyncio.run(
            fake_sandbox.files.write(
                "/workspace/final_output/report.md",
                report_content,
            )
        )

        # Run publisher.sync() against the fake sandbox.
        publisher = SandboxResourcePublisher(
            sandbox=fake_sandbox,  # type: ignore[arg-type]
            run_id=run.id,
            task_execution_id=prepared.execution_id,
            blob_root=blob_root,
        )
        created = asyncio.run(publisher.sync())
        assert len(created) >= 1, "Publisher should have created at least one resource"
        assert created[0].kind == RunResourceKind.REPORT

        # Verify content hash.
        expected_hash = hashlib.sha256(report_content).hexdigest()
        assert created[0].content_hash == expected_hash

        # Finalize the task execution.
        exec_svc.finalize_success(
            FinalizeTaskExecutionCommand(
                execution_id=prepared.execution_id,
                output_text="Stub report written",
            )
        )
        completed_tasks.append((task_desc, prepared))

    # ── Propagate ──────────────────────────────────────────────────
    prop_svc = TaskPropagationService()
    for task_desc, prepared in completed_tasks:
        prop_svc.propagate(
            PropagateTaskCompletionCommand(
                run_id=run.id,
                definition_id=persisted.definition_id,
                task_id=task_desc.task_id,
                execution_id=prepared.execution_id,
            )
        )

    # ── Evaluate (in-process criterion) ────────────────────────────
    for task_desc, prepared in completed_tasks:
        criterion = StubReportExistsCriterion()
        ctx = EvaluationContext(
            run_id=run.id,
            task=BenchmarkTask(
                task_key="smoke-research-001",
                instance_key="default",
                description="smoke test",
            ),
            worker_result=WorkerOutput(output="Stub report written"),
            metadata={"execution_id": prepared.execution_id},
        )
        result = asyncio.run(criterion.evaluate(ctx))
        assert result.passed, f"Criterion failed: {result.feedback}"
        assert result.score == 1.0

        # Persist evaluation.
        eval_record = RunTaskEvaluation(
            run_id=run.id,
            definition_task_id=task_desc.task_id,
            definition_evaluator_id=uuid4(),
            score=result.score,
            passed=result.passed,
            feedback=result.feedback,
        )
        with get_session() as session:
            session.add(eval_record)
            session.commit()

    # ── Finalize Workflow ──────────────────────────────────────────
    final_svc = WorkflowFinalizationService()
    finalized = final_svc.finalize(
        FinalizeWorkflowCommand(
            run_id=run.id,
            definition_id=persisted.definition_id,
        )
    )

    # ── Assert final state ─────────────────────────────────────────
    with get_session() as session:
        final_run = session.get(RunRecord, run.id)
        assert final_run is not None
        assert final_run.status == RunStatus.COMPLETED

        executions = list(
            session.exec(
                select(RunTaskExecution).where(
                    RunTaskExecution.run_id == run.id,
                )
            ).all()
        )
        assert len(executions) >= 1
        for ex in executions:
            assert ex.status == TaskExecutionStatus.COMPLETED

        evaluations = list(
            session.exec(
                select(RunTaskEvaluation).where(
                    RunTaskEvaluation.run_id == run.id,
                )
            ).all()
        )
        assert len(evaluations) >= 1
        for ev in evaluations:
            assert ev.score is not None
            assert ev.passed is True

        # Verify RunResource rows exist.
        resources = list(
            session.exec(select(RunResource).where(RunResource.run_id == run.id)).all()
        )
        assert len(resources) >= 1
        report_resources = [r for r in resources if r.kind == RunResourceKind.REPORT.value]
        assert len(report_resources) >= 1
        assert report_resources[0].content_hash is not None
