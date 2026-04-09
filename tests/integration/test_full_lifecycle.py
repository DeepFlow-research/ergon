"""B.5 Execution smoke test: full lifecycle without a live Inngest server.

Exercises the same code paths the Inngest functions use, calling services
directly to simulate the event-driven flow:
  construct -> validate -> persist -> initialize workflow -> execute tasks
  -> propagate -> finalize workflow -> verify telemetry
"""

import asyncio

from arcane_builtins.benchmarks.smoke_test.benchmark import SmokeTestBenchmark
from arcane_builtins.evaluators.rubrics.stub_rubric import StubRubric
from arcane_builtins.registry import WORKERS
from arcane_builtins.workers.baselines.stub_worker import StubWorker
from h_arcane.api import Experiment
from h_arcane.api.task_types import BenchmarkTask
from h_arcane.api.worker_context import WorkerContext
from h_arcane.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionTask,
)
from h_arcane.core.persistence.shared.db import create_all_tables, get_session
from h_arcane.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from h_arcane.core.persistence.telemetry.models import (
    RunRecord,
    RunTaskExecution,
    RunTaskStateEvent,
)
from h_arcane.core.runtime.services.orchestration_dto import (
    FinalizeTaskExecutionCommand,
    FinalizeWorkflowCommand,
    InitializeWorkflowCommand,
    PrepareTaskExecutionCommand,
    PropagateTaskCompletionCommand,
)
from h_arcane.core.runtime.services.run_service import create_run
from h_arcane.core.runtime.services.task_execution_service import TaskExecutionService
from h_arcane.core.runtime.services.task_propagation_service import TaskPropagationService
from h_arcane.core.runtime.services.workflow_finalization_service import (
    WorkflowFinalizationService,
)
from h_arcane.core.runtime.services.workflow_initialization_service import (
    WorkflowInitializationService,
)
from sqlmodel import select


def test_full_lifecycle():
    """Prove: construct -> validate -> persist -> run -> execute -> complete."""

    # Ensure all tables exist (fresh SQLite)
    create_all_tables()

    # ── Phase A: Construct + Validate + Persist ─────────────────────
    benchmark = SmokeTestBenchmark(workflow="flat", task_count=2)
    worker = StubWorker(name="test", model="openai:gpt-4o")
    rubric = StubRubric()

    experiment = Experiment.from_single_worker(
        benchmark=benchmark,
        worker=worker,
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
    initialized = init_svc.initialize(
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
    assert run_row.status == RunStatus.EXECUTING
    session.close()

    # ── Phase B: Execute Each Task ──────────────────────────────────
    exec_svc = TaskExecutionService()
    completed_executions = []

    for task_desc in initialized.initial_ready_tasks:
        # Prepare
        prepared = exec_svc.prepare(
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
            f"[EXEC] Prepared task {prepared.task_key} "
            f"(worker={prepared.worker_type}, model={prepared.model_target})"
        )

        # Construct worker from registry (same as worker_execute Inngest fn)
        worker_cls = WORKERS[prepared.worker_type]
        live_worker = worker_cls(
            name=prepared.worker_binding_key or "worker",
            model=prepared.model_target,
        )

        # Execute
        task_data = BenchmarkTask(
            task_key=prepared.task_key,
            instance_key="",
            description=prepared.task_description,
        )
        ctx = WorkerContext(
            run_id=run.id,
            task_id=task_desc.task_id,
            execution_id=prepared.execution_id,
            sandbox_id="test-sandbox",
        )
        result = asyncio.run(live_worker.execute(task_data, context=ctx))
        assert result.success
        print(f"[EXEC] Task {prepared.task_key} -> output: {result.output[:50]}")

        # Finalize success
        exec_svc.finalize_success(
            FinalizeTaskExecutionCommand(
                execution_id=prepared.execution_id,
                output_text=result.output,
            )
        )
        completed_executions.append((task_desc, prepared))

    # ── Phase B: Propagate Completions ──────────────────────────────
    prop_svc = TaskPropagationService()
    for task_desc, prepared in completed_executions:
        prop_result = prop_svc.propagate(
            PropagateTaskCompletionCommand(
                run_id=run.id,
                definition_id=persisted.definition_id,
                task_id=task_desc.task_id,
                execution_id=prepared.execution_id,
            )
        )
        print(
            f"[PROP] Task {task_desc.task_key}: "
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
    assert final_run.status == RunStatus.COMPLETED
    print(f"[VERIFY] Run status: {final_run.status}")

    # Task executions exist and are COMPLETED
    executions = list(
        session.exec(
            select(RunTaskExecution).where(RunTaskExecution.run_id == run.id)
        ).all()
    )
    assert len(executions) == 2
    for ex in executions:
        assert ex.status == TaskExecutionStatus.COMPLETED
        assert ex.output_text is not None
    print(f"[VERIFY] {len(executions)} task executions, all COMPLETED")

    # State events exist
    events = list(
        session.exec(
            select(RunTaskStateEvent).where(RunTaskStateEvent.run_id == run.id)
        ).all()
    )
    assert len(events) > 0
    statuses = {e.new_status for e in events}
    assert "pending" in statuses
    assert "completed" in statuses
    print(f"[VERIFY] {len(events)} state events recorded (statuses: {statuses})")

    session.close()
    print("\n=== B.5 EXECUTION SMOKE TEST: PASS ===")


if __name__ == "__main__":
    import os
    os.environ["ARCANE_DATABASE_URL"] = "sqlite:///test_smoke.db"
    try:
        os.remove("test_smoke.db")
    except FileNotFoundError:
        pass  # slopcop: ignore[no-pass-except]
    test_full_lifecycle()
