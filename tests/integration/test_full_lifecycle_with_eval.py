"""C.4 Full evaluation smoke test.

Exercises the complete pipeline including evaluation:
  construct -> validate -> persist -> initialize -> execute tasks
  -> evaluate (dispatch + run criteria + aggregate) -> finalize -> verify scores

Calls the same services the Inngest functions call, without requiring a live server.
"""

import asyncio

from arcane_builtins.benchmarks.smoke_test.benchmark import SmokeTestBenchmark
from arcane_builtins.evaluators.rubrics.stub_rubric import StubRubric
from arcane_builtins.registry import EVALUATORS, WORKERS
from arcane_builtins.workers.baselines.stub_worker import StubWorker
from h_arcane.api import Experiment
from h_arcane.api.task_types import BenchmarkTask
from h_arcane.api.worker_context import WorkerContext
from h_arcane.core.persistence.shared.db import create_all_tables, get_session
from h_arcane.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from h_arcane.core.persistence.telemetry.models import (
    RunRecord,
    RunTaskEvaluation,
    RunTaskExecution,
    RunTaskStateEvent,
)
from h_arcane.core.runtime.evaluation.evaluation_schemas import TaskEvaluationContext
from h_arcane.core.runtime.services.evaluation_dto import DispatchEvaluatorsCommand
from h_arcane.core.runtime.services.evaluator_dispatch_service import (
    EvaluatorDispatchService,
)
from h_arcane.core.runtime.services.orchestration_dto import (
    FinalizeTaskExecutionCommand,
    FinalizeWorkflowCommand,
    InitializeWorkflowCommand,
    PrepareTaskExecutionCommand,
    PropagateTaskCompletionCommand,
)
from h_arcane.core.runtime.services.rubric_evaluation_service import (
    RubricEvaluationService,
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


class InProcessCriterionExecutor:
    """Simple in-process executor for testing (no Inngest step.run)."""

    async def execute_all(self, task_context, benchmark_name, criteria):
        # Deferred: avoid circular import
        from h_arcane.api.evaluation_context import EvaluationContext
        # Deferred: avoid circular import
        from h_arcane.api.results import WorkerResult as WR

        results = []
        for spec in criteria:
            criterion = spec.criterion
            eval_ctx = EvaluationContext(
                run_id=task_context.run_id,
                task=BenchmarkTask(task_key="", instance_key="", description=""),
                worker_result=WR(output=task_context.agent_reasoning),
                sandbox_id=None,
                metadata={},
            )
            result = await criterion.evaluate(eval_ctx)
            results.append(result)
        return results


def test_full_lifecycle_with_evaluation():
    """Prove: construct -> validate -> persist -> run -> execute -> evaluate -> score."""

    create_all_tables()

    # ── Construct + Validate + Persist ──────────────────────────────
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
    print(f"[PERSIST] Definition {persisted.definition_id} ({persisted.task_count} tasks)")

    # ── Create Run + Initialize ─────────────────────────────────────
    run = create_run(persisted)
    print(f"[RUN] Created {run.id}")

    init_svc = WorkflowInitializationService()
    initialized = init_svc.initialize(
        InitializeWorkflowCommand(run_id=run.id, definition_id=persisted.definition_id)
    )
    print(f"[INIT] {initialized.total_tasks} tasks, {len(initialized.initial_ready_tasks)} ready")

    # ── Execute Tasks ───────────────────────────────────────────────
    exec_svc = TaskExecutionService()
    completed_tasks = []

    for task_desc in initialized.initial_ready_tasks:
        prepared = exec_svc.prepare(
            PrepareTaskExecutionCommand(
                run_id=run.id,
                definition_id=persisted.definition_id,
                task_id=task_desc.task_id,
            )
        )
        worker_cls = WORKERS[prepared.worker_type]
        live_worker = worker_cls(
            name=prepared.worker_binding_key or "w",
            model=prepared.model_target,
        )
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
        exec_svc.finalize_success(
            FinalizeTaskExecutionCommand(
                execution_id=prepared.execution_id,
                output_text=result.output,
            )
        )
        completed_tasks.append((task_desc, prepared, result))
        print(f"[EXEC] Task {prepared.task_key} completed")

    # ── Propagate ───────────────────────────────────────────────────
    prop_svc = TaskPropagationService()
    for task_desc, prepared, _ in completed_tasks:
        prop_svc.propagate(
            PropagateTaskCompletionCommand(
                run_id=run.id,
                definition_id=persisted.definition_id,
                task_id=task_desc.task_id,
                execution_id=prepared.execution_id,
            )
        )

    # ── Evaluate ────────────────────────────────────────────────────
    dispatch_svc = EvaluatorDispatchService()

    for task_desc, prepared, worker_result in completed_tasks:
        dispatch = dispatch_svc.prepare_dispatch(
            DispatchEvaluatorsCommand(
                run_id=run.id,
                definition_id=persisted.definition_id,
                task_id=task_desc.task_id,
                execution_id=prepared.execution_id,
            )
        )
        print(
            f"[EVAL] Task {task_desc.task_key}: "
            f"{dispatch.evaluators_found} evaluators found, "
            f"{len(dispatch.valid_evaluators)} valid"
        )

        for eval_payload in dispatch.valid_evaluators:
            evaluator_cls = EVALUATORS.get(eval_payload.evaluator_type)
            if evaluator_cls is None:
                print(f"  [EVAL] Unknown evaluator type: {eval_payload.evaluator_type}")
                continue

            evaluator = evaluator_cls(name=eval_payload.evaluator_binding_key)

            executor = InProcessCriterionExecutor()
            eval_service = RubricEvaluationService(criterion_executor=executor)

            task_context = TaskEvaluationContext(
                run_id=run.id,
                task_input="",
                agent_reasoning=worker_result.output,
            )
            task_for_eval = BenchmarkTask(
                task_key=task_desc.task_key,
                instance_key="",
                description="",
            )

            service_result = asyncio.run(
                eval_service.evaluate(
                    task_context=task_context,
                    evaluator=evaluator,
                    task=task_for_eval,
                    benchmark_name="smoke-test",
                )
            )
            eval_result = service_result.result
            print(
                f"  [EVAL] {eval_payload.evaluator_binding_key}: "
                f"score={eval_result.score}, passed={eval_result.passed}"
            )

            # Deferred: avoid circular import
            from h_arcane.core.runtime.inngest.evaluate_task_run import (
                _build_evaluation_summary,
            )
            summary = _build_evaluation_summary(service_result, evaluation_input="")

            session = get_session()
            evaluation = RunTaskEvaluation(
                run_id=run.id,
                definition_task_id=task_desc.task_id,
                definition_evaluator_id=eval_payload.evaluator_id,
                score=eval_result.score,
                passed=eval_result.passed,
                feedback=eval_result.feedback,
                summary_json=summary.model_dump(mode="json"),
            )
            session.add(evaluation)
            session.commit()
            session.close()

    # ── Finalize Workflow ───────────────────────────────────────────
    final_svc = WorkflowFinalizationService()
    finalized = final_svc.finalize(
        FinalizeWorkflowCommand(run_id=run.id, definition_id=persisted.definition_id)
    )
    print(
        f"[FINAL] score={finalized.final_score}, "
        f"normalized={finalized.normalized_score}, "
        f"evaluators={finalized.evaluators_count}"
    )

    # ── Verify ──────────────────────────────────────────────────────
    session = get_session()

    final_run = session.get(RunRecord, run.id)
    assert final_run.status == RunStatus.COMPLETED, f"Expected COMPLETED, got {final_run.status}"
    print(f"[VERIFY] Run status: {final_run.status}")

    executions = list(
        session.exec(select(RunTaskExecution).where(RunTaskExecution.run_id == run.id)).all()
    )
    assert len(executions) == 2
    for ex in executions:
        assert ex.status == TaskExecutionStatus.COMPLETED
    print(f"[VERIFY] {len(executions)} task executions, all COMPLETED")

    evaluations = list(
        session.exec(select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run.id)).all()
    )
    assert len(evaluations) == 2, f"Expected 2 evaluations, got {len(evaluations)}"
    for ev in evaluations:
        assert ev.score is not None
        assert ev.passed is not None
    print(f"[VERIFY] {len(evaluations)} task evaluations with scores")

    assert finalized.evaluators_count == 2
    assert finalized.final_score is not None
    assert finalized.final_score > 0
    print(f"[VERIFY] Final score: {finalized.final_score}")

    events = list(
        session.exec(select(RunTaskStateEvent).where(RunTaskStateEvent.run_id == run.id)).all()
    )
    statuses = {e.new_status for e in events}
    assert "pending" in statuses
    assert "completed" in statuses
    print(f"[VERIFY] {len(events)} state events (statuses: {statuses})")

    session.close()
    print("\n=== C.4 FULL EVALUATION SMOKE TEST: PASS ===")


if __name__ == "__main__":
    import os

    os.environ["ARCANE_DATABASE_URL"] = "sqlite:///test_eval_smoke.db"
    try:
        os.remove("test_eval_smoke.db")
    except FileNotFoundError:
        pass  # slopcop: ignore[no-pass-except]
    test_full_lifecycle_with_evaluation()
