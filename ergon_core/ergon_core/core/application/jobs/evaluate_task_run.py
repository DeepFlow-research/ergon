"""Per-evaluator Inngest function — thin id-only payload, run-tier reads.

Receives one ``TaskEvaluateRequest`` per evaluator from
`execute_task._fan_out_evaluators`.
The payload only carries identity (``run_id`` + ``task_id`` +
``execution_id`` + ``evaluator_index``); everything else is
reconstructed locally from the run-tier read boundary:

- execution row + stamped ``sandbox_id`` ← ``session.get(RunTaskExecution)``
- typed Task view ← ``WorkflowGraphRepository.node(..., sandbox_id=...)``
- persisted ``WorkerOutput`` ← ``WorkerOutputRepository.load``
- evaluator instance ← ``task.evaluators[payload.evaluator_index]``

Criteria run inline via ``EvaluationService.evaluate``: no
``evaluator runner`` Protocol, no per-criterion ``ctx.step.run``.
The Inngest retry unit is now the whole evaluator, because the
orchestrator already gives one ``step.invoke`` per evaluator via
the synchronous-fanout boundary in `execute_task`.

Sandbox lifetime: this function detaches its local runtime handle after
evaluation, but it never terminates the external sandbox. The external
sandbox is terminated exactly once by the sibling ``sandbox_cleanup``
function after ``execute_task`` emits a terminal task event.
"""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

import inngest

from ergon_core.api.criterion.context import CriterionContext
from ergon_core.core.application.evaluation.service import EvaluationService
from ergon_core.core.application.graph.repository import WorkflowGraphRepository
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

if TYPE_CHECKING:
    from ergon_core.api.rubric import Evaluator
    from ergon_core.core.application.graph.models import RunGraphNodeView

logger = logging.getLogger(__name__)
_evaluation_persistence = EvaluationService()


def _evaluator_binding_key(evaluator: "Evaluator", evaluator_index: int) -> str:
    return evaluator.name or f"inline-{evaluator_index}"


async def run_evaluate_task_run_job(
    ctx: inngest.Context,
    payload: TaskEvaluateRequest,
) -> EvaluateTaskRunResult:
    """Per-evaluator fanout target. Thin id-only payload."""

    del ctx  # The orchestrator provides the evaluator-level retry boundary.

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
        worker_output = await WorkerOutputRepository().load(
            session,
            execution_id=execution_id,
        )
        task = view.task
        if evaluator_index < 0 or evaluator_index >= len(task.evaluators):
            raise ContractViolationError(
                f"evaluator_index {evaluator_index} out of range for task "
                f"{task.task_slug!r} (has {len(task.evaluators)} evaluators)",
                run_id=run_id,
                task_id=task_id,
                execution_id=execution_id,
            )
        evaluator = task.evaluators[evaluator_index]
        binding_key = _evaluator_binding_key(evaluator, evaluator_index)

    context = CriterionContext(
        run_id=run_id,
        task_id=task.task_id,
        execution_id=execution_id,
        task=task,
        worker_result=worker_output,
    )

    try:
        return await _run_evaluation(
            evaluator=evaluator,
            context=context,
            binding_key=binding_key,
            evaluator_index=evaluator_index,
            view=view,
            run_id=run_id,
            task_id=task_id,
            execution_id=execution_id,
            span_start=span_start,
        )
    finally:
        # Release the local sandbox handle as soon as criteria finish.
        # The orchestrator owns external sandbox termination, and sibling
        # eval workers still need it alive until fanout resolves.
        if task.sandbox.is_live:
            await task.sandbox.detach()


async def _run_evaluation(
    *,
    evaluator: "Evaluator",
    context: CriterionContext,
    binding_key: str,
    evaluator_index: int,
    view: "RunGraphNodeView",
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID,
    span_start: datetime,
) -> EvaluateTaskRunResult:
    """Run the evaluator, persist, emit the trace span. Sandbox lifetime
    is the caller's concern (see ``run_evaluate_task_run_job``'s
    ``finally`` block) — extracting this helper keeps the eval body free
    of nested try/except blocks.
    """

    try:
        service_result = await _evaluation_persistence.evaluate(
            context=context,
            evaluator=evaluator,
        )
    except Exception as exc:  # slopcop: ignore[no-broad-except]
        logger.exception(
            "evaluate_task_run failed run_id=%s task_id=%s index=%s",
            run_id,
            task_id,
            evaluator_index,
        )
        await _evaluation_persistence.persist_failure(
            run_id=run_id,
            task_execution_id=execution_id,
            task_id=view.task_id,
            binding_key=binding_key,
            exc=exc,
        )
        return EvaluateTaskRunResult(
            score=0.0,
            passed=False,
            evaluator_name=binding_key,
        )

    result = service_result.result
    persisted = await _evaluation_persistence.persist_success(
        run_id=run_id,
        task_execution_id=execution_id,
        task_id=view.task_id,
        binding_key=binding_key,
        service_result=service_result,
    )
    await get_dashboard_emitter().task_evaluation_updated(
        run_id=run_id,
        task_id=view.task_id,
        evaluation=persisted.dashboard_dto,
    )

    # Trace span needs the evaluator_id for stable key derivation;
    # reuse the persistence lookup so the span key matches the
    # `run_task_evaluations.definition_evaluator_id` FK on the
    # row persist_success just wrote.
    with get_session() as session:
        evaluator_id = _evaluation_persistence.lookup_evaluator_id(
            session,
            run_id,
            binding_key,
            evaluator_type=evaluator.type_slug,
            snapshot_json=evaluator.model_dump(mode="json"),
        )
    get_trace_sink().emit_span(
        CompletedSpan(
            name="evaluation.task",
            context=evaluation_task_context(run_id, view.task_id, execution_id, evaluator_id),
            start_time=span_start,
            end_time=datetime.now(UTC),
            attributes={
                "run_id": str(run_id),
                "task_id": str(view.task_id),
                "execution_id": str(execution_id),
                "evaluator_id": str(evaluator_id),
                "evaluator_binding_key": binding_key,
                "evaluator_type": type(evaluator).type_slug,
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
