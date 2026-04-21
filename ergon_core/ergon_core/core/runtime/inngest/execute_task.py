"""Inngest function: task execution orchestrator.

Prepares a task, invokes sandbox/worker/persist child functions, then
finalizes. Emits TaskCompletedEvent on success, TaskFailedEvent on failure.
"""

import logging
from datetime import UTC, datetime

import inngest
from ergon_core.core.runtime.errors import ConfigurationError, ContractViolationError
from ergon_core.core.runtime.events.task_events import (
    SANDBOX_SKIPPED,
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskReadyEvent,
)
from ergon_core.core.runtime.inngest_client import RUN_CANCEL, TASK_CANCEL, inngest_client
from ergon_core.core.runtime.services.child_function_payloads import (
    PersistOutputsRequest,
    SandboxSetupRequest,
    WorkerExecuteRequest,
)
from ergon_core.core.runtime.services.inngest_function_results import (
    PersistOutputsResult,
    SandboxReadyResult,
    TaskExecuteResult,
    WorkerExecuteResult,
)
from ergon_core.core.runtime.services.orchestration_dto import (
    FailTaskExecutionCommand,
    FinalizeTaskExecutionCommand,
    PreparedTaskExecution,
    PrepareTaskExecutionCommand,
)
from ergon_core.core.runtime.services.task_execution_service import TaskExecutionService
from ergon_core.core.runtime.tracing import (
    CompletedSpan,
    get_trace_sink,
    task_execute_context,
    truncate_text,
)

logger = logging.getLogger(__name__)


# retries=0: side effects (sandbox creation, model API calls, DB writes)
# would duplicate on retry. Failure propagates via TaskFailedEvent.
# Concurrency bounded by E2B sandbox quota and Postgres connection pool.
@inngest_client.create_function(
    fn_id="task-execute",
    trigger=inngest.TriggerEvent(event="task/ready"),
    cancel=[*RUN_CANCEL, *TASK_CANCEL],
    retries=0,
    concurrency=[inngest.Concurrency(limit=15)],
    output_type=TaskExecuteResult,
)
async def execute_task_fn(ctx: inngest.Context) -> TaskExecuteResult:
    payload = TaskReadyEvent.model_validate(ctx.event.data)
    logger.info("task-execute run_id=%s task_id=%s", payload.run_id, payload.task_id)
    span_start = datetime.now(UTC)

    svc = TaskExecutionService()

    async def _prepare() -> PreparedTaskExecution:
        return await svc.prepare(
            PrepareTaskExecutionCommand(
                run_id=payload.run_id,
                definition_id=payload.definition_id,
                task_id=payload.task_id,
                node_id=payload.node_id,
            )
        )

    prepared = await ctx.step.run("prepare-execution", _prepare, output_type=PreparedTaskExecution)

    if prepared.skipped:
        logger.info(
            "task-execute skipped task_id=%s reason=%s",
            payload.task_id,
            prepared.skip_reason,
        )
        await inngest_client.send(
            inngest.Event(
                name=TaskCompletedEvent.name,
                data=TaskCompletedEvent(
                    run_id=payload.run_id,
                    definition_id=payload.definition_id,
                    task_id=payload.task_id,
                    execution_id=prepared.execution_id,
                    sandbox_id=SANDBOX_SKIPPED,
                    node_id=prepared.node_id,
                ).model_dump(mode="json"),
            )
        )
        return TaskExecuteResult(
            run_id=payload.run_id,
            task_id=payload.task_id,
            execution_id=prepared.execution_id,
            success=True,
            skipped=True,
            skip_reason=prepared.skip_reason,
        )

    task_sandbox_id: str = SANDBOX_SKIPPED
    try:
        # Deferred: child function modules register with Inngest at import
        # time. Eager cross-imports between registered modules cause cycles.
        from ergon_core.core.runtime.inngest.persist_outputs import persist_outputs_fn

        # Deferred: avoid circular import
        from ergon_core.core.runtime.inngest.sandbox_setup import sandbox_setup_fn

        # Deferred: avoid circular import
        from ergon_core.core.runtime.inngest.worker_execute import worker_execute_fn

        sandbox_result: SandboxReadyResult = await ctx.step.invoke(
            "sandbox-setup",
            function=sandbox_setup_fn,
            data=SandboxSetupRequest(
                run_id=payload.run_id,
                definition_id=payload.definition_id,
                task_id=payload.task_id,
                benchmark_type=prepared.benchmark_type,
            ).model_dump(),
        )
        if not sandbox_result.sandbox_id:
            raise ContractViolationError(
                "sandbox-setup returned empty sandbox_id",
                run_id=payload.run_id,
                task_id=payload.task_id,
            )
        task_sandbox_id = sandbox_result.sandbox_id

        if not prepared.worker_type:
            raise ConfigurationError(
                "Task has no worker_type configured",
                run_id=payload.run_id,
                task_id=payload.task_id,
            )

        worker_result: WorkerExecuteResult = await ctx.step.invoke(
            "worker-execute",
            function=worker_execute_fn,
            data=WorkerExecuteRequest(
                run_id=payload.run_id,
                definition_id=payload.definition_id,
                task_id=payload.task_id,
                execution_id=prepared.execution_id,
                sandbox_id=sandbox_result.sandbox_id,
                task_key=prepared.task_key,
                task_description=prepared.task_description,
                worker_binding_key=prepared.worker_binding_key or "",
                worker_type=prepared.worker_type,
                model_target=prepared.model_target,
                benchmark_type=prepared.benchmark_type,
                node_id=prepared.node_id,
            ).model_dump(),
        )

        if not worker_result.success:
            raise RuntimeError(worker_result.error or "Worker execution failed")

        persist_result: PersistOutputsResult = await ctx.step.invoke(
            "persist-outputs",
            function=persist_outputs_fn,
            data=PersistOutputsRequest(
                run_id=payload.run_id,
                definition_id=payload.definition_id,
                task_id=payload.task_id,
                execution_id=prepared.execution_id,
                sandbox_id=sandbox_result.sandbox_id,
                output_dir=sandbox_result.output_dir,
                benchmark_type=prepared.benchmark_type,
                worker_output_text=worker_result.output_text,
            ).model_dump(),
        )

        await svc.finalize_success(
            FinalizeTaskExecutionCommand(
                execution_id=prepared.execution_id,
                output_text=worker_result.output_text,
            )
        )

        await inngest_client.send(
            inngest.Event(
                name=TaskCompletedEvent.name,
                data=TaskCompletedEvent(
                    run_id=payload.run_id,
                    definition_id=payload.definition_id,
                    task_id=payload.task_id,
                    execution_id=prepared.execution_id,
                    sandbox_id=task_sandbox_id,
                    node_id=prepared.node_id,
                ).model_dump(mode="json"),
            )
        )

        get_trace_sink().emit_span(
            CompletedSpan(
                name="task.execute",
                context=task_execute_context(payload.run_id, payload.task_id),
                start_time=span_start,
                end_time=datetime.now(UTC),
                attributes={
                    "run_id": str(payload.run_id),
                    "definition_id": str(payload.definition_id),
                    "task_id": str(payload.task_id),
                    "execution_id": str(prepared.execution_id),
                    "task_key": prepared.task_key,
                    "benchmark_type": prepared.benchmark_type,
                    "worker_type": prepared.worker_type or "",
                    "worker_binding_key": prepared.worker_binding_key or "",
                    "model_target": prepared.model_target or "",
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

        await svc.finalize_failure(
            FailTaskExecutionCommand(
                execution_id=prepared.execution_id,
                run_id=payload.run_id,
                task_id=payload.task_id,
                error_message=error_msg,
            )
        )

        await inngest_client.send(
            inngest.Event(
                name=TaskFailedEvent.name,
                data=TaskFailedEvent(
                    run_id=payload.run_id,
                    definition_id=payload.definition_id,
                    task_id=payload.task_id,
                    execution_id=prepared.execution_id,
                    error=error_msg,
                    sandbox_id=task_sandbox_id,
                    node_id=prepared.node_id,
                ).model_dump(mode="json"),
            )
        )

        get_trace_sink().emit_span(
            CompletedSpan(
                name="task.execute",
                context=task_execute_context(payload.run_id, payload.task_id),
                start_time=span_start,
                end_time=datetime.now(UTC),
                status_code="error",
                status_message=truncate_text(error_msg),
                attributes={
                    "run_id": str(payload.run_id),
                    "definition_id": str(payload.definition_id),
                    "task_id": str(payload.task_id),
                    "execution_id": str(prepared.execution_id),
                    "task_key": prepared.task_key,
                    "benchmark_type": prepared.benchmark_type,
                    "skipped": False,
                    "status": "failed",
                    "error": truncate_text(error_msg),
                },
            )
        )

        raise inngest.NonRetriableError(message=error_msg) from exc
