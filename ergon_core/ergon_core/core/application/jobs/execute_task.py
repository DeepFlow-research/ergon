"""Inngest function: task execution orchestrator.

Prepares a task, invokes sandbox/worker/persist child functions, fans
out per-evaluator invocations of ``evaluate_task_run``, then finalizes.
Emits TaskCompletedEvent on success, TaskFailedEvent on failure.

**Sandbox lifetime ownership.** This function — not ``worker_execute``
— is the orchestrator that wraps the *entire* sandbox lifetime in a
single ``try/finally``. The flow is:

    sandbox-setup    →  acquires external sandbox, returns sandbox_id
    worker-execute   →  runs the worker against the sandbox
    persist-outputs  →  uploads artifacts (still needs the sandbox)
    _fan_out_evaluators
                     →  ctx.group.parallel(partial(ctx.step.invoke, …))
                        per evaluator; each evaluator reattaches to
                        the sandbox by id
    [emit task/completed]
    finally: terminate_sandbox_by_id(...)

The `ctx.group.parallel` await is what makes the invariant work: the
orchestrator cannot reach the `finally` until every per-evaluator
`step.invoke` returns, so the external sandbox is guaranteed alive
throughout evaluation *and* guaranteed terminated immediately after.
Pre-PR-4, termination lived in a sibling Inngest function
(`check_evaluators`) that fired on `task/completed` — under retry
replay that sibling could terminate the sandbox while eval workers
were still running against it. PR 4 collapses both responsibilities
into this one `try/finally`.

**Why the orchestrator is `execute_task`, not `worker_execute`** (the
PR 4 plan code put fanout in `worker_execute`): in our codebase
`worker_execute` runs *between* `sandbox_setup` and `persist_outputs`
as sibling Inngest functions, so terminating in
`worker_execute.finally` would kill the sandbox before
`persist_outputs` could upload artifacts. See PR 4 plan
`05-pr-04-inline-criteria.md` § "Implementation Note —
Bridge-Everything Approach" for the location rationale.
"""

from __future__ import annotations

import logging
import traceback
from datetime import UTC, datetime
from functools import partial
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # The architectural boundary `test_inngest_jobs_and_handlers_stay_split`
    # forbids application/jobs/*.py from importing `inngest` at runtime —
    # the infrastructure handlers own the framework coupling. Typing
    # cross-boundary symbols (`inngest.Context`, `inngest.Function`)
    # through TYPE_CHECKING keeps annotations precise without giving
    # this module a runtime dependency on the SDK.
    import inngest

from ergon_core.core.application.graph.repository import WorkflowGraphRepository
from ergon_core.core.application.jobs.models import (
    PersistOutputsRequest,
    PersistOutputsResult,
    SandboxReadyResult,
    SandboxSetupRequest,
    TaskEvaluateRequest,
    TaskExecuteResult,
    WorkerExecuteJobRequest,
    WorkerExecuteJobResult,
)
from ergon_core.core.application.tasks.execution import TaskExecutionService
from ergon_core.core.application.workflows.orchestration import (
    FailTaskExecutionCommand,
    FinalizeTaskExecutionCommand,
    PreparedTaskExecution,
    PrepareTaskExecutionCommand,
)
from ergon_core.core.infrastructure.inngest.client import InngestEvent, inngest_client
from ergon_core.core.infrastructure.inngest.errors import ContractViolationError, NonRetriableError
from ergon_core.core.infrastructure.sandbox.lifecycle import terminate_sandbox_by_id
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunRecord
from ergon_core.core.application.events.task_events import (
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskReadyEvent,
)
from ergon_core.core.infrastructure.tracing import (
    CompletedSpan,
    get_trace_sink,
    task_execute_context,
    truncate_text,
)

logger = logging.getLogger(__name__)


async def _prepare_execution(
    ctx: inngest.Context,
    svc: TaskExecutionService,
    payload: TaskReadyEvent,
) -> PreparedTaskExecution:
    async def _prepare() -> PreparedTaskExecution:
        return await svc.prepare(
            PrepareTaskExecutionCommand(
                run_id=payload.run_id,
                definition_id=payload.definition_id,
                task_id=payload.task_id,
                node_id=payload.node_id,
            )
        )

    return await ctx.step.run("prepare-execution", _prepare, output_type=PreparedTaskExecution)


async def _setup_sandbox(
    ctx: inngest.Context,
    payload: TaskReadyEvent,
    prepared: PreparedTaskExecution,
    sandbox_setup_function: inngest.Function,
) -> SandboxReadyResult:
    # Dynamic subtasks have no static task_id. Use node_id as the sandbox key
    # so each subtask gets its own isolated sandbox slot in the manager registry.
    sandbox_task_key = payload.task_id or prepared.node_id
    return await ctx.step.invoke(
        "sandbox-setup",
        function=sandbox_setup_function,
        data=SandboxSetupRequest(
            run_id=payload.run_id,
            definition_id=payload.definition_id,
            task_id=sandbox_task_key,
            benchmark_type=prepared.benchmark_type,
            sandbox_slug=_sandbox_slug_for_run(payload.run_id),
        ).model_dump(),
    )


def _sandbox_slug_for_run(run_id) -> str | None:
    session = get_session()
    try:
        run = session.get(RunRecord, run_id)
        return None if run is None else run.sandbox_slug
    finally:
        session.close()


async def _run_worker(
    ctx: inngest.Context,
    payload: TaskReadyEvent,
    prepared: PreparedTaskExecution,
    sandbox_result: SandboxReadyResult,
    worker_execute_function: inngest.Function,
) -> WorkerExecuteJobResult:
    return await ctx.step.invoke(
        "worker-execute",
        function=worker_execute_function,
        data=WorkerExecuteJobRequest(
            run_id=payload.run_id,
            definition_id=payload.definition_id,
            task_id=payload.task_id,
            execution_id=prepared.execution_id,
            sandbox_id=sandbox_result.sandbox_id,
            task_slug=prepared.task_slug,
            task_description=prepared.task_description,
            assigned_worker_slug=prepared.assigned_worker_slug,
            worker_type=prepared.worker_type,
            model_target=prepared.model_target,
            benchmark_type=prepared.benchmark_type,
            node_id=prepared.node_id,
        ).model_dump(),
    )


async def _fan_out_evaluators(
    ctx: inngest.Context,
    payload: TaskReadyEvent,
    prepared: PreparedTaskExecution,
    evaluate_task_run_function: inngest.Function,
) -> None:
    """Synchronously fan out per-evaluator Inngest invocations.

    This is PR 4's headline invariant. The orchestrator suspends on
    `ctx.group.parallel(...)` until every per-evaluator
    `ctx.step.invoke(...)` returns; once it resumes, control falls
    through to the `finally` block in ``run_execute_task_job`` and
    the external sandbox is terminated. Same shape as
    `InngestCriterionExecutor.execute_all` (the v1 per-criterion
    parallelism), just lifted one level up to per-evaluator.

    ``ctx.group.parallel`` over a tuple of ``partial(ctx.step.invoke, ...)``
    is the Inngest-native parallelism primitive. Using
    ``asyncio.gather`` over `step.invoke` coroutines bypasses the
    SDK's parallel-step bookkeeping and isn't guaranteed to give
    proper parallelism.

    Evaluator count comes from ``task.evaluator_binding_keys`` today.
    In PR 5 it comes from ``len(task.evaluators)`` — the loop body
    stays the same, only the source of the bound list changes (see
    `06-pr-05-object-bound-api.md` Task 2). We load the task view
    without ``sandbox_id=`` here because the orchestrator side doesn't
    need a live ``_runtime`` handle on the inflated Task; the eval
    workers each call ``graph_repo.node(..., sandbox_id=...)`` on their
    own side to attach.
    """

    canonical_task_id = payload.task_id or prepared.node_id
    with get_session() as session:
        view = await WorkflowGraphRepository().node(
            session,
            run_id=payload.run_id,
            task_id=canonical_task_id,
        )
    evaluator_count = len(view.task.evaluator_binding_keys)
    if evaluator_count == 0:
        return

    await ctx.group.parallel(
        tuple(
            partial(
                ctx.step.invoke,
                f"eval-{i}",
                function=evaluate_task_run_function,
                data=TaskEvaluateRequest(
                    run_id=payload.run_id,
                    task_id=canonical_task_id,
                    execution_id=prepared.execution_id,
                    evaluator_index=i,
                ).model_dump(mode="json"),
            )
            for i in range(evaluator_count)
        )
    )


async def _persist_outputs(
    ctx: inngest.Context,
    payload: TaskReadyEvent,
    prepared: PreparedTaskExecution,
    sandbox_result: SandboxReadyResult,
    persist_outputs_function: inngest.Function,
) -> PersistOutputsResult:
    output_task_key = payload.task_id or prepared.node_id
    return await ctx.step.invoke(
        "persist-outputs",
        function=persist_outputs_function,
        data=PersistOutputsRequest(
            run_id=payload.run_id,
            definition_id=payload.definition_id,
            task_id=output_task_key,
            execution_id=prepared.execution_id,
            sandbox_id=sandbox_result.sandbox_id,
            output_dir=sandbox_result.output_dir,
            benchmark_type=prepared.benchmark_type,
            sandbox_slug=_sandbox_slug_for_run(payload.run_id),
        ).model_dump(),
    )


async def _emit_task_completed(
    payload: TaskReadyEvent,
    prepared: PreparedTaskExecution,
    sandbox_id: str,
) -> None:
    await inngest_client.send(
        InngestEvent(
            name=TaskCompletedEvent.name,
            data=TaskCompletedEvent(
                run_id=payload.run_id,
                definition_id=payload.definition_id,
                task_id=payload.task_id,
                execution_id=prepared.execution_id,
                sandbox_id=sandbox_id,
                node_id=prepared.node_id,
            ).model_dump(mode="json"),
        )
    )


async def _emit_task_failed(
    payload: TaskReadyEvent,
    prepared: PreparedTaskExecution,
    error_message: str,
    sandbox_id: str | None,
) -> None:
    await inngest_client.send(
        InngestEvent(
            name=TaskFailedEvent.name,
            data=TaskFailedEvent(
                run_id=payload.run_id,
                definition_id=payload.definition_id,
                task_id=payload.task_id,
                execution_id=prepared.execution_id,
                error=error_message,
                sandbox_id=sandbox_id,
                node_id=prepared.node_id,
            ).model_dump(mode="json"),
        )
    )


# retries=0: side effects (sandbox creation, model API calls, DB writes)
# would duplicate on retry. Failure propagates via TaskFailedEvent.
# Concurrency bounded by E2B sandbox quota and Postgres connection pool.
async def run_execute_task_job(
    ctx: inngest.Context,
    payload: TaskReadyEvent,
    *,
    sandbox_setup_function: inngest.Function,
    worker_execute_function: inngest.Function,
    persist_outputs_function: inngest.Function,
    evaluate_task_run_function: inngest.Function,
) -> TaskExecuteResult:
    logger.info("task-execute run_id=%s task_id=%s", payload.run_id, payload.task_id)
    span_start = datetime.now(UTC)

    svc = TaskExecutionService()

    # Hoist ``prepared`` so the except handler can branch on prepare vs
    # post-prepare failure (``finalize_failure`` + ``TaskFailedEvent`` only
    # when ``prepared`` is set). See
    # docs/bugs/open/2026-04-23-inngest-function-failures.md § A.
    prepared: PreparedTaskExecution | None = None
    # ``None`` until sandbox-setup returns. ``TaskFailedEvent.sandbox_id`` is
    # now ``str | None`` so a pre-sandbox failure carries ``None`` instead of
    # the old ``"skipped"`` magic string.
    task_sandbox_id: str | None = None
    try:
        prepared = await _prepare_execution(ctx, svc, payload)

        if prepared.skipped:
            raise ContractViolationError(
                "Skipped task execution cannot emit task/completed without a real sandbox_id. "
                "Introduce a first-class task/skipped event before supporting skipped tasks.",
                run_id=payload.run_id,
                task_id=payload.task_id,
            )

        sandbox_result = await _setup_sandbox(ctx, payload, prepared, sandbox_setup_function)
        if not sandbox_result.sandbox_id:
            raise ContractViolationError(
                "sandbox-setup returned empty sandbox_id",
                run_id=payload.run_id,
                task_id=payload.task_id,
            )
        task_sandbox_id = sandbox_result.sandbox_id

        worker_result = await _run_worker(
            ctx, payload, prepared, sandbox_result, worker_execute_function
        )

        if not worker_result.success:
            await _persist_outputs(ctx, payload, prepared, sandbox_result, persist_outputs_function)
            error_msg = worker_result.error or "Worker execution failed"
            await svc.finalize_failure(
                FailTaskExecutionCommand(
                    execution_id=prepared.execution_id,
                    run_id=payload.run_id,
                    task_id=payload.task_id,
                    error_message=error_msg,
                    error_json=worker_result.error_json,
                )
            )
            await _emit_task_failed(payload, prepared, error_msg, task_sandbox_id)
            return TaskExecuteResult(
                run_id=payload.run_id,
                task_id=payload.task_id,
                execution_id=prepared.execution_id,
                success=False,
                error=error_msg,
            )

        persist_result = await _persist_outputs(
            ctx, payload, prepared, sandbox_result, persist_outputs_function
        )

        # Synchronous fanout. `ctx.group.parallel` keeps the sandbox
        # alive through every per-evaluator Inngest invocation; the
        # orchestrator cannot reach the `finally` (sandbox termination)
        # until all evaluators return.
        await _fan_out_evaluators(ctx, payload, prepared, evaluate_task_run_function)

        await svc.finalize_success(
            FinalizeTaskExecutionCommand(
                execution_id=prepared.execution_id,
                final_assistant_message=worker_result.final_assistant_message,
            )
        )

        # task_sandbox_id was populated from sandbox-setup above; the
        # contract violation was already raised if it was missing. Assert via
        # ContractViolationError rather than `assert` so the check survives
        # `python -O`.
        if task_sandbox_id is None:
            raise ContractViolationError(
                "task_sandbox_id is None after sandbox-setup completed",
                run_id=payload.run_id,
                task_id=payload.task_id,
            )
        await _emit_task_completed(payload, prepared, task_sandbox_id)

        get_trace_sink().emit_span(
            CompletedSpan(
                name="task.execute",
                context=task_execute_context(payload.run_id, prepared.node_id),
                start_time=span_start,
                end_time=datetime.now(UTC),
                attributes={
                    "run_id": str(payload.run_id),
                    "definition_id": str(payload.definition_id),
                    "task_id": str(prepared.node_id),
                    "execution_id": str(prepared.execution_id),
                    "task_slug": prepared.task_slug,
                    "benchmark_type": prepared.benchmark_type,
                    "worker_type": prepared.worker_type,
                    "assigned_worker_slug": prepared.assigned_worker_slug,
                    "model_target": prepared.model_target,
                    "skipped": False,
                    "status": "completed",
                },
            )
        )

        return TaskExecuteResult(
            run_id=payload.run_id,
            task_id=payload.task_id,
            execution_id=prepared.execution_id,
            success=True,
            outputs_count=persist_result.outputs_count,
        )

    except Exception as exc:  # slopcop: ignore[no-broad-except]
        error_msg = str(exc)
        logger.exception("task-execute failed task_id=%s: %s", payload.task_id, error_msg)

        if prepared is not None:
            # Post-prepare failure: we have an execution row to finalize
            # and a full TaskFailedEvent to emit.
            await svc.finalize_failure(
                FailTaskExecutionCommand(
                    execution_id=prepared.execution_id,
                    run_id=payload.run_id,
                    task_id=payload.task_id,
                    error_message=error_msg,
                    error_json={
                        "message": error_msg,
                        "exception_type": type(exc).__name__,
                        "phase": "task_execute",
                        "stack": "".join(
                            traceback.format_exception(type(exc), exc, exc.__traceback__)
                        ),
                        "context": {
                            "task_slug": str(prepared.task_slug),
                            "assigned_worker_slug": str(prepared.assigned_worker_slug),
                            "worker_type": str(prepared.worker_type),
                            "model_target": str(prepared.model_target),
                            "node_id": str(prepared.node_id),
                            "execution_id": str(prepared.execution_id),
                        },
                    },
                )
            )

            await _emit_task_failed(payload, prepared, error_msg, task_sandbox_id)

            get_trace_sink().emit_span(
                CompletedSpan(
                    name="task.execute",
                    context=task_execute_context(payload.run_id, prepared.node_id),
                    start_time=span_start,
                    end_time=datetime.now(UTC),
                    status_code="error",
                    status_message=truncate_text(error_msg),
                    attributes={
                        "run_id": str(payload.run_id),
                        "definition_id": str(payload.definition_id),
                        "task_id": str(prepared.node_id),
                        "execution_id": str(prepared.execution_id),
                        "task_slug": prepared.task_slug,
                        "benchmark_type": prepared.benchmark_type,
                        "skipped": False,
                        "status": "failed",
                        "error": truncate_text(error_msg),
                    },
                )
            )
        else:
            # Prepare itself raised — no execution row, no task_slug, no
            # reliable task_id (``payload.task_id`` may be ``None`` for
            # dynamic subtasks, which is why prepare raised in the
            # first place).  Log loudly; the span + event emission
            # requires a non-null task_id which we don't have here.  The
            # run_graph_node stays in RUNNING on this branch. The
            # ``node_id``/``task_id`` identity cleanup in README (Open refactors)
            # targets this ambiguity. Without *this* hoist, even the traceback
            # was invisible — the function just silently died in Inngest.
            logger.error(
                "task-execute: prepare raised for task_id=%s node_id=%s — "
                "no execution row to finalize",
                payload.task_id,
                payload.node_id,
            )

        raise NonRetriableError(message=error_msg) from exc

    finally:
        # Orchestrator-owned sandbox release. Everything past
        # sandbox-setup terminates here regardless of which path raised
        # — eval workers ran inside `ctx.group.parallel` above, so
        # the sandbox is still alive at this point. The v1 release
        # site lived in a *sibling* Inngest function
        # (`check_evaluators._terminate_sandbox`), which could
        # terminate while eval workers were still running under retry
        # replay; PR 4 fixes that bug by moving release into the same
        # function that acquired the sandbox.
        #
        # Forward shape: when `lifecycle_hub` lands (PR 5 or 6,
        # depending on how the Sandbox ABC settles), this call site
        # becomes ``await lifecycle_hub.release(sandbox)`` — same
        # ownership boundary, prettier API. The
        # `terminate_sandbox_by_id` helper itself is on the PR 11 Δ.7
        # deletion list once nothing else imports it.
        if task_sandbox_id is not None:
            # TODO(PR 5 or 6): swap for `await lifecycle_hub.release(sandbox)`
            # once the hub primitive lands; same ownership boundary, cleaner API.
            termination = await terminate_sandbox_by_id(task_sandbox_id)
            logger.info(
                "task-execute sandbox cleanup sandbox_id=%s terminated=%s reason=%s",
                termination.sandbox_id,
                termination.terminated,
                termination.reason,
            )
