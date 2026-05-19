"""Per-evaluator Inngest function — thin id-only payload, run-tier reads.

Receives one ``TaskEvaluateRequest`` per evaluator from the
orchestrator's `asyncio.gather` (see `execute_task._fan_out_evaluators`).
The payload only carries identity (``run_id`` + ``task_id`` +
``execution_id`` + ``evaluator_index``); everything else is
reconstructed locally from the run-tier read boundary:

- execution row + stamped ``sandbox_id`` ← ``session.get(RunTaskExecution)``
- typed Task view ← ``WorkflowGraphRepository.node(..., sandbox_id=...)``
- persisted ``WorkerOutput`` ← ``WorkerOutputRepository.load``
- evaluator instance ← ``task.evaluators[payload.evaluator_index]``
  (PR 5 object-bound; the PR 4 ``_evaluator_bridge`` multi-hop lookup
  was retired alongside the Worker/Evaluator → Pydantic conversion)

Criteria run inline via ``EvaluationService.evaluate``: no
``CriterionExecutor`` Protocol, no per-criterion ``ctx.step.run``.
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
from ergon_core.core.persistence.telemetry.models import RunRecord, RunTaskExecution

if TYPE_CHECKING:
    from ergon_core.api.rubric import Evaluator
    from ergon_core.core.application.graph.models import RunGraphNodeView

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
        worker_output = await WorkerOutputRepository().load(
            session,
            execution_id=execution_id,
        )
        task = view.task
        if task.evaluators:
            if evaluator_index < 0 or evaluator_index >= len(task.evaluators):
                raise ContractViolationError(
                    f"evaluator_index {evaluator_index} out of range for task "
                    f"{task.task_slug!r} (has {len(task.evaluators)} evaluators)",
                    run_id=run_id,
                    task_id=task_id,
                    execution_id=execution_id,
                )
            evaluator = task.evaluators[evaluator_index]
            binding_key = evaluator.name
        else:
            # TODO(PR 11): delete this branch + the sibling module. See
            # `_legacy_evaluator_bridge.py` docstring for the migration ledger.
            from ergon_core.core.application.jobs._legacy_evaluator_bridge import (
                legacy_evaluator_from_binding,
            )

            if evaluator_index < 0 or evaluator_index >= len(task.evaluator_binding_keys):
                raise ContractViolationError(
                    f"evaluator_index {evaluator_index} out of range for task "
                    f"{task.task_slug!r} (has {len(task.evaluator_binding_keys)} "
                    "evaluator binding keys)",
                    run_id=run_id,
                    task_id=task_id,
                    execution_id=execution_id,
                )
            binding_key = task.evaluator_binding_keys[evaluator_index]
            evaluator = legacy_evaluator_from_binding(
                session,
                run_id=run_id,
                binding_key=binding_key,
            )

    context = CriterionContext(
        run_id=run_id,
        task_id=task.task_id,
        execution_id=execution_id,
        task=task,
        worker_result=worker_output,
        sandbox_id=execution.sandbox_id,
    )
    if task.sandbox is None:
        # TODO(PR 11): delete this branch + the sibling module. The
        # object-bound path attaches `_runtime` via `task.sandbox`;
        # legacy TaskSpec snapshots have no `task.sandbox`, so the
        # bridge constructs an equivalent runtime from the benchmark's
        # sandbox manager. See `_legacy_evaluator_bridge.py` docstring.
        from ergon_core.core.application.jobs._legacy_evaluator_bridge import (
            legacy_inject_criterion_runtime,
        )

        with get_session() as _sess:
            _run = _sess.get(RunRecord, run_id)
            benchmark_type = _run.benchmark_type if _run is not None else ""
        context = legacy_inject_criterion_runtime(
            public_context=context,
            benchmark_type=benchmark_type,
            run_id=run_id,
            task_id=task_id or task.task_id,
            sandbox_id=execution.sandbox_id,
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
        # PR 5: release the local sandbox handle as soon as criteria
        # finish. The external sandbox stays running — the orchestrator
        # (`execute_task`) owns termination, and other eval workers
        # invoked from the same `ctx.group.parallel` need the sandbox
        # alive until the gather resolves. `detach()` raises if there's
        # no live runtime, but `Task.from_definition` with `sandbox_id`
        # always attaches — see `Sandbox.from_definition`'s contract.
        if task.sandbox is not None and task.sandbox.is_live:
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
        _evaluation_persistence.persist_failure(
            run_id=run_id,
            node_id=view.node_id,
            task_execution_id=execution_id,
            definition_task_id=view.definition_task_id,
            binding_key=binding_key,
            exc=exc,
        )
        return EvaluateTaskRunResult(
            score=0.0,
            passed=False,
            evaluator_name=binding_key,
        )

    result = service_result.result
    persisted = _evaluation_persistence.persist_success(
        run_id=run_id,
        node_id=view.node_id,
        task_execution_id=execution_id,
        definition_task_id=view.definition_task_id,
        binding_key=binding_key,
        service_result=service_result,
    )
    await get_dashboard_emitter().task_evaluation_updated(
        run_id=run_id,
        task_id=view.node_id,
        evaluation=persisted.dashboard_dto,
    )

    # Trace span needs the evaluator_id for stable key derivation;
    # reuse the persistence lookup so the span key matches the
    # `run_task_evaluations.definition_evaluator_id` FK on the
    # row persist_success just wrote.
    with get_session() as session:
        evaluator_id = _evaluation_persistence.lookup_evaluator_id(session, run_id, binding_key)
    get_trace_sink().emit_span(
        CompletedSpan(
            name="evaluation.task",
            context=evaluation_task_context(run_id, view.node_id, execution_id, evaluator_id),
            start_time=span_start,
            end_time=datetime.now(UTC),
            attributes={
                "run_id": str(run_id),
                "task_id": str(view.node_id),
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
