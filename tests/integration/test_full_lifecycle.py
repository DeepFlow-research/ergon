"""B.5 Execution smoke test: full lifecycle without a live Inngest server.

Exercises the same code paths the Inngest functions use, calling services
directly to simulate the event-driven flow:
  construct -> validate -> persist -> initialize workflow -> execute tasks
  -> propagate -> finalize workflow -> verify telemetry
"""

from ergon_builtins.benchmarks.smoke_test.benchmark import SmokeTestBenchmark
from ergon_builtins.evaluators.rubrics.stub_rubric import StubRubric
from ergon_builtins.registry import WORKERS
from ergon_core.api import Experiment, Worker, WorkerSpec
from ergon_core.api.results import WorkerOutput
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.worker_context import WorkerContext
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionTask,
)
from ergon_core.core.persistence.shared.db import ensure_db, get_session
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunTaskExecution,
)
from ergon_core.core.persistence.telemetry.repositories import GenerationTurnRepository
from ergon_core.core.runtime.services.orchestration_dto import (
    FinalizeTaskExecutionCommand,
    FinalizeWorkflowCommand,
    InitializeWorkflowCommand,
    PrepareTaskExecutionCommand,
    PropagateTaskCompletionCommand,
)
from ergon_core.core.runtime.services.run_service import create_run
from ergon_core.core.runtime.services.task_execution_service import TaskExecutionService
from ergon_core.core.runtime.services.task_propagation_service import TaskPropagationService
from ergon_core.core.runtime.services.workflow_finalization_service import (
    WorkflowFinalizationService,
)
from ergon_core.core.runtime.services.workflow_initialization_service import (
    WorkflowInitializationService,
)
from sqlmodel import select


async def _run_worker(worker: Worker, task: BenchmarkTask, ctx: WorkerContext) -> WorkerOutput:
    """Consume the worker's async generator, persist turns, return output.

    Mirrors the logic in worker_execute_fn without the Inngest/sandbox overhead.
    """
    repo = GenerationTurnRepository()
    turn_count = 0
    async for turn in worker.execute(task, context=ctx):
        with get_session() as session:
            await repo.persist_single(
                session,
                run_id=ctx.run_id,
                execution_id=ctx.execution_id,
                worker_binding_key=worker.name,
                turn=turn,
                turn_index=turn_count,
                execution_outcome="success",
            )
        turn_count += 1
    return worker.get_output(ctx)


async def test_full_lifecycle():
    """Prove: construct -> validate -> persist -> run -> execute -> complete."""

    ensure_db()

    # ── Phase A: Construct + Validate + Persist ─────────────────────
    benchmark = SmokeTestBenchmark(workflow="flat", task_count=2)
    # reason: RFC 2026-04-22 §1 — ``Experiment`` holds ``WorkerSpec``
    # descriptors at config time; the live ``Worker`` is built per-task
    # via the registry factory inside ``worker_execute`` (mirrored at
    # Phase B below).
    spec = WorkerSpec(worker_slug="stub-worker", name="test", model="openai:gpt-4o")
    rubric = StubRubric()

    experiment = Experiment.from_single_worker(
        benchmark=benchmark,
        worker=spec,
        evaluators={"default": rubric},
    )
    experiment.validate()

    persisted = experiment.persist()
    assert persisted.definition_id is not None
    assert persisted.benchmark_type == "smoke-test"
    assert persisted.task_count == 2
    assert persisted.instance_count == 1
    print(f"[PERSIST] Definition {persisted.definition_id} with {persisted.task_count} tasks")

    # Verify definition rows
    session = get_session()
    defn = session.get(ExperimentDefinition, persisted.definition_id)
    assert defn is not None
    tasks = list(
        session.exec(
            select(ExperimentDefinitionTask).where(
                ExperimentDefinitionTask.experiment_definition_id == persisted.definition_id
            )
        ).all()
    )
    assert len(tasks) == 2
    session.close()

    # ── Phase B: Create Run ─────────────────────────────────────────
    run = create_run(persisted)
    assert run.status == RunStatus.PENDING
    print(f"[RUN] Created run {run.id} (status={run.status})")

    # ── Phase B: Initialize Workflow ────────────────────────────────
    init_svc = WorkflowInitializationService()
    initialized = await init_svc.initialize(
        InitializeWorkflowCommand(
            run_id=run.id,
            definition_id=persisted.definition_id,
        )
    )
    assert initialized.total_tasks == 2
    assert len(initialized.initial_ready_tasks) == 2  # no dependencies = all ready
    print(
        f"[INIT] {initialized.total_tasks} tasks, "
        f"{len(initialized.initial_ready_tasks)} initially ready"
    )

    # Verify run is now EXECUTING
    session = get_session()
    run_row = session.get(RunRecord, run.id)
    assert run_row is not None
    assert run_row.status == RunStatus.EXECUTING
    session.close()

    # ── Phase B: Execute Each Task ──────────────────────────────────
    exec_svc = TaskExecutionService()
    completed_executions = []

    for task_desc in initialized.initial_ready_tasks:
        # Prepare
        prepared = await exec_svc.prepare(
            PrepareTaskExecutionCommand(
                run_id=run.id,
                definition_id=persisted.definition_id,
                task_id=task_desc.task_id,
            )
        )
        assert not prepared.skipped
        assert prepared.worker_type is not None
        assert prepared.execution_id is not None
        print(
            f"[EXEC] Prepared task {prepared.task_slug} "
            f"(worker={prepared.worker_type}, model={prepared.model_target})"
        )

        # Construct worker from registry (same as worker_execute Inngest fn).
        # reason: RFC 2026-04-22 §1 — base ``Worker.__init__`` requires
        # ``task_id`` / ``sandbox_id``; every registered subclass forwards
        # them to ``super().__init__``, so the factory signature is uniform.
        worker_cls = WORKERS[prepared.worker_type]
        live_worker = worker_cls(
            name=prepared.assigned_worker_slug or "worker",
            model=prepared.model_target,
            task_id=task_desc.task_id,
            sandbox_id="test-sandbox",
        )

        # Execute
        task_data = BenchmarkTask(
            task_slug=prepared.task_slug,
            instance_key="",
            description=prepared.task_description,
        )
        ctx = WorkerContext(
            run_id=run.id,
            task_id=task_desc.task_id,
            execution_id=prepared.execution_id,
            sandbox_id="test-sandbox",
        )
        result = await _run_worker(live_worker, task_data, ctx)
        assert result.success
        print(f"[EXEC] Task {prepared.task_slug} -> output: {result.output[:50]}")

        # Finalize success
        await exec_svc.finalize_success(
            FinalizeTaskExecutionCommand(
                execution_id=prepared.execution_id,
                final_assistant_message=result.output,
            )
        )
        completed_executions.append((task_desc, prepared))

    # ── Phase B: Propagate Completions ──────────────────────────────
    prop_svc = TaskPropagationService()
    for task_desc, prepared in completed_executions:
        prop_result = await prop_svc.propagate(
            PropagateTaskCompletionCommand(
                run_id=run.id,
                definition_id=persisted.definition_id,
                task_id=task_desc.task_id,
                execution_id=prepared.execution_id,
            )
        )
        print(
            f"[PROP] Task {task_desc.task_slug}: "
            f"{len(prop_result.ready_tasks)} newly ready, "
            f"terminal={prop_result.workflow_terminal_state}"
        )

    # ── Phase B: Finalize Workflow ──────────────────────────────────
    final_svc = WorkflowFinalizationService()
    finalized = final_svc.finalize(
        FinalizeWorkflowCommand(
            run_id=run.id,
            definition_id=persisted.definition_id,
        )
    )
    print(
        f"[FINAL] score={finalized.final_score}, "
        f"normalized={finalized.normalized_score}, "
        f"evaluators={finalized.evaluators_count}"
    )

    # ── Verify Final State ──────────────────────────────────────────
    session = get_session()

    # Run is COMPLETED
    final_run = session.get(RunRecord, run.id)
    assert final_run is not None
    assert final_run.status == RunStatus.COMPLETED
    print(f"[VERIFY] Run status: {final_run.status}")

    # Task executions exist and are COMPLETED
    executions = list(
        session.exec(select(RunTaskExecution).where(RunTaskExecution.run_id == run.id)).all()
    )
    assert len(executions) == 2
    for ex in executions:
        assert ex.status == TaskExecutionStatus.COMPLETED
        assert ex.final_assistant_message is not None
    print(f"[VERIFY] {len(executions)} task executions, all COMPLETED")

    session.close()
    print("\n=== B.5 EXECUTION SMOKE TEST: PASS ===")


if __name__ == "__main__":
    import asyncio
    import os

    os.environ.setdefault(
        "ERGON_DATABASE_URL",
        "postgresql://ergon_core:ergon_core_dev@localhost:5433/ergon_core_test",
    )
    asyncio.run(test_full_lifecycle())
