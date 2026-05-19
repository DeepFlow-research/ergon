"""Per-evaluator Inngest function — thin id-only payload, run-tier reads.

Receives one ``TaskEvaluateRequest`` per evaluator from the
orchestrator's `asyncio.gather` (see `execute_task._fan_out_evaluators`).
The payload only carries identity (``run_id`` + ``task_id`` +
``execution_id`` + ``evaluator_index``); everything else is
reconstructed locally from the run-tier read boundary:

- execution row + stamped ``sandbox_id`` ← ``session.get(RunTaskExecution)``
- typed Task view ← ``WorkflowGraphRepository.node(..., sandbox_id=...)``
- persisted ``WorkerOutput`` ← ``WorkerOutputRepository.load``
- evaluator instance ← `_evaluator_bridge.resolve_evaluator` (PR 4-only
  multi-hop lookup; PR 5 collapses it to `task.evaluators[i]` once the
  Task carries `Evaluator` instances directly — see
  `_evaluator_bridge.py` module docstring for the lift plan)

Criteria run inline via ``EvaluationService.evaluate``: no
``CriterionExecutor`` Protocol, no per-criterion ``ctx.step.run``.
The Inngest retry unit is now the whole evaluator, because the
orchestrator already gives one ``step.invoke`` per evaluator via
the synchronous-fanout boundary in `execute_task`.

Sandbox lifetime: this function **never** terminates or detaches a
sandbox. `execute_task`'s `try/finally` owns external sandbox
lifetime end-to-end (release happens after every fan-out invoke
returns). PR 5 (Task 4c § Step 1) adds an eval-side
``await task.sandbox.detach()`` once `Sandbox` exists as a real ABC,
to release the *local* `_runtime` handle — the external sandbox stays
owned by the orchestrator.
"""

import logging
from datetime import UTC, datetime

import inngest

from ergon_core.api.criterion.context import CriterionContext
from ergon_core.core.application.evaluation.service import EvaluationService
from ergon_core.core.application.graph.repository import WorkflowGraphRepository
from ergon_core.core.application.jobs._evaluator_bridge import resolve_evaluator
from ergon_core.core.application.jobs.models import (
    EvaluateTaskRunResult,
    TaskEvaluateRequest,
)
from ergon_core.core.application.tasks.repository import WorkerOutputRepository
from ergon_core.core.infrastructure.dashboard.provider import get_dashboard_emitter
from ergon_core.core.infrastructure.inngest.errors import ContractViolationError
from ergon_core.core.infrastructure.tracing import (
    CompletedSpan,
    evaluation_task_context,
    get_trace_sink,
)
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunTaskExecution

logger = logging.getLogger(__name__)
_evaluation_persistence = EvaluationService()


async def run_evaluate_task_run_job(
    ctx: inngest.Context,
    payload: TaskEvaluateRequest,
) -> EvaluateTaskRunResult:
    """Per-evaluator fanout target. Thin id-only payload."""

    del ctx  # PR 4: no per-criterion step.run; the orchestrator already
    # provides the retry/concurrency boundary at the evaluator level.

    span_start = datetime.now(UTC)
    run_id = payload.run_id
    task_id = payload.task_id
    execution_id = payload.execution_id
    evaluator_index = payload.evaluator_index

    with get_session() as session:
        execution = session.get(RunTaskExecution, execution_id)
        if execution is None:
            raise ContractViolationError(
                f"RunTaskExecution {execution_id} not found",
                run_id=run_id,
                task_id=task_id,
                execution_id=execution_id,
            )
        view = await WorkflowGraphRepository().node(
            session,
            run_id=run_id,
            task_id=task_id,
            sandbox_id=execution.sandbox_id,
        )
        bound = resolve_evaluator(
            session,
            run_id=run_id,
            task=view.task,
            evaluator_index=evaluator_index,
        )
        worker_output = await WorkerOutputRepository().load(
            session,
            execution_id=execution_id,
        )

    task = view.task
    context = CriterionContext(
        run_id=run_id,
        task_id=task.task_id,
        execution_id=execution_id,
        task=task,
        worker_result=worker_output,
        sandbox_id=execution.sandbox_id,
    )

    try:
        service_result = await _evaluation_persistence.evaluate(
            context=context,
            evaluator=bound.evaluator,
        )
    except Exception as exc:  # slopcop: ignore[no-broad-except]
        logger.exception(
            "evaluate_task_run failed run_id=%s task_id=%s index=%s",
            run_id,
            task_id,
            evaluator_index,
        )
        _evaluation_persistence.persist_failure(
            run_id=run_id,
            node_id=view.node_id,
            task_execution_id=execution_id,
            definition_task_id=view.definition_task_id,
            evaluator_id=bound.evaluator_id,
            evaluator_name=bound.binding_key,
            exc=exc,
        )
        return EvaluateTaskRunResult(
            score=0.0,
            passed=False,
            evaluator_name=bound.binding_key,
        )

    result = service_result.result
    persisted = _evaluation_persistence.persist_success(
        run_id=run_id,
        node_id=view.node_id,
        task_execution_id=execution_id,
        definition_task_id=view.definition_task_id,
        evaluator_id=bound.evaluator_id,
        service_result=service_result,
    )
    await get_dashboard_emitter().task_evaluation_updated(
        run_id=run_id,
        task_id=view.node_id,
        evaluation=persisted.dashboard_dto,
    )

    get_trace_sink().emit_span(
        CompletedSpan(
            name="evaluation.task",
            context=evaluation_task_context(run_id, view.node_id, execution_id, bound.evaluator_id),
            start_time=span_start,
            end_time=datetime.now(UTC),
            attributes={
                "run_id": str(run_id),
                "task_id": str(view.node_id),
                "execution_id": str(execution_id),
                "evaluator_id": str(bound.evaluator_id),
                "evaluator_type": bound.evaluator_type,
                "evaluator_index": evaluator_index,
                "score": result.score,
                "passed": result.passed,
                "stages_evaluated": persisted.summary.stages_evaluated,
                "stages_passed": persisted.summary.stages_passed,
            },
        )
    )

    return EvaluateTaskRunResult(
        score=result.score,
        passed=result.passed,
        evaluator_name=result.evaluator_name,
    )
