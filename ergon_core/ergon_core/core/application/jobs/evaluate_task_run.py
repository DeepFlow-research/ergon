"""Per-evaluator Inngest function — thin id-only payload, run-tier reads.

PR 4 reshape: ``evaluate_task_run`` takes a thin ``TaskEvaluateRequest``
(``run_id`` + ``task_id`` + ``execution_id`` + ``evaluator_index``)
and reloads everything else through the run-tier read boundary:

- execution row + stamped ``sandbox_id`` via ``session.get(RunTaskExecution)``
- typed Task view via ``WorkflowGraphRepository.node(..., sandbox_id=...)``
- persisted ``WorkerOutput`` via ``WorkerOutputRepository.load``
- evaluator instance via the PR 4 ``_evaluator_bridge`` (TODO(PR 5):
  drop the bridge once ``task.evaluators`` is object-bound)

The criterion runner is ``EvaluationService.evaluate_inline`` — no
``CriterionExecutor`` Protocol on this path. The Inngest retry unit
shifts from "per criterion ``step.run``" to "per evaluator
``step.invoke``" because the orchestrator (``worker_execute``) now
fans out one Inngest invocation per evaluator.

Sandbox lifetime: the eval worker does **not** terminate or detach
sandboxes. ``worker_execute``'s ``try/finally`` owns external sandbox
lifetime through the orchestrator's ``asyncio.gather``. PR 5 adds
``task.sandbox.detach()`` for the local handle once ``Sandbox`` is a
real ABC.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from ergon_core.api.criterion.context import CriterionContext
from ergon_core.core.application.evaluation.service import EvaluationService
from ergon_core.core.application.graph.repository import WorkflowGraphRepository
from ergon_core.core.application.jobs._evaluator_bridge import resolve_evaluator
from ergon_core.core.application.jobs.models import (
    EvaluateTaskRunResult,
    TaskEvaluateRequest,
)
from ergon_core.core.infrastructure.dashboard.provider import get_dashboard_emitter
from ergon_core.core.infrastructure.inngest.errors import ContractViolationError
from ergon_core.core.infrastructure.tracing import (
    CompletedSpan,
    evaluation_task_context,
    get_trace_sink,
)
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunTaskExecution
from ergon_core.core.application.tasks.repository import WorkerOutputRepository

logger = logging.getLogger(__name__)
_evaluation_persistence = EvaluationService()


async def run_evaluate_task_run_job(
    ctx: Any,
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
        service_result = await _evaluation_persistence.evaluate_inline(
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
            context=evaluation_task_context(
                run_id, view.node_id, execution_id, bound.evaluator_id
            ),
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
