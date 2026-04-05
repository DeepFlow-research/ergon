"""Task execution Inngest function.

Orchestrates single task execution by invoking child functions.
"""

from functools import partial
from uuid import UUID

import inngest

from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.infrastructure.tracing import (
    CompletedSpan,
    TraceContext,
    get_trace_sink,
    task_execute_context,
)
from h_arcane.core._internal.task.events import (
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskReadyEvent,
)
from h_arcane.core._internal.task.inngest_functions.persist_outputs import persist_outputs_fn
from h_arcane.core._internal.task.inngest_functions.sandbox_setup import sandbox_setup_fn
from h_arcane.core._internal.task.inngest_functions.worker_execute import worker_execute_fn
from h_arcane.core._internal.task.requests import (
    PersistOutputsRequest,
    SandboxSetupRequest,
    WorkerExecuteRequest,
)
from h_arcane.core._internal.task.results import (
    PersistOutputsResult,
    SandboxReadyResult,
    TaskExecuteResult,
    WorkerExecuteResult,
)
from h_arcane.core._internal.task.services import TaskExecutionService
from h_arcane.core._internal.task.services.dto import (
    FailTaskExecutionCommand,
    FinalizeTaskExecutionCommand,
    PrepareTaskExecutionCommand,
    PreparedTaskExecution,
)
from h_arcane.core._internal.utils import require_not_none, utcnow
from h_arcane.core.settings import settings
from h_arcane.core.status import TaskStatus, TaskTrigger
from h_arcane.core.dashboard import dashboard_emitter


@inngest_client.create_function(
    fn_id="task-execute",
    trigger=inngest.TriggerEvent(event=TaskReadyEvent.name),
    retries=0,  # Tasks should not auto-retry (user decides retry strategy)
    concurrency=[inngest.Concurrency(limit=15, scope="fn")],
    output_type=TaskExecuteResult,
)
async def task_execute(ctx: inngest.Context) -> TaskExecuteResult:
    """
    Orchestrate single task execution.

    This function:
    1. Loads context and validates task (inlined)
    2. Creates execution record and marks running
    3. Invokes sandbox_setup child function
    4. Invokes worker_execute child function
    5. Invokes persist_outputs child function
    6. Completes execution and emits event
    """
    payload = TaskReadyEvent.model_validate(ctx.event.data)
    run_id = payload.run_id
    experiment_id = payload.experiment_id
    task_id = payload.task_id
    trace_sink = get_trace_sink()
    service_trace_context = task_execute_context(
        run_id,
        task_id,
        attributes={"experiment_id": experiment_id},
    )

    prepared = await ctx.step.run(
        "prepare-task-execution",
        lambda: TaskExecutionService(
            trace_sink=trace_sink,
            trace_context=service_trace_context,
        ).prepare(
            PrepareTaskExecutionCommand(
                run_id=run_id,
                experiment_id=experiment_id,
                task_id=task_id,
            )
        ),
        output_type=PreparedTaskExecution,
    )

    if prepared.skipped:
        return TaskExecuteResult(
            run_id=run_id,
            task_id=task_id,
            success=True,
            skipped=True,
            skip_reason=prepared.skip_reason,
        )

    execution_id = prepared.execution_id
    if execution_id is None:
        raise ValueError(f"Prepared execution for task {task_id} is missing execution_id")
    trace_context = task_execute_context(
        run_id,
        task_id,
        execution_id=execution_id,
        attributes={
            "experiment_id": experiment_id,
            "task_name": prepared.task_name,
            "parent_task_id": prepared.parent_task_id,
            "benchmark_name": prepared.benchmark_name,
        },
    )

    # Emit dashboard task running event
    await ctx.step.run(
        "emit-dashboard-task-running",
        partial(
            _emit_dashboard_task_running,
            run_id,
            task_id,
            prepared.task_name,
            prepared.parent_task_id,
        ),
    )

    try:
        # Invoke: Setup sandbox
        sandbox_result: SandboxReadyResult = await ctx.step.invoke(
            step_id="invoke-sandbox-setup",
            function=sandbox_setup_fn,
            data=SandboxSetupRequest(
                run_id=run_id,
                experiment_id=experiment_id,
                task_id=task_id,
                benchmark_name=prepared.benchmark_name,
                input_resource_ids=prepared.input_resource_ids,
                envs={"EXA_API_KEY": settings.exa_api_key},
            ).model_dump(mode="json"),
        )

        # Invoke: Execute worker
        worker_result: WorkerExecuteResult = await ctx.step.invoke(
            step_id="invoke-worker-execute",
            function=worker_execute_fn,
            data=WorkerExecuteRequest(
                run_id=run_id,
                task_id=task_id,
                execution_id=execution_id,
                sandbox_id=sandbox_result.sandbox_id,
                task_description=prepared.task_description,
                input_resource_ids=prepared.input_resource_ids,
                benchmark_name=prepared.benchmark_name,
                max_questions=prepared.max_questions,
            ).model_dump(mode="json"),
        )

        # Check if worker execution failed
        if not worker_result.success:
            raise Exception(worker_result.error or "Worker execution failed")

        # Invoke: Persist outputs
        persist_result: PersistOutputsResult = await ctx.step.invoke(
            step_id="invoke-persist-outputs",
            function=persist_outputs_fn,
            data=PersistOutputsRequest(
                run_id=run_id,
                task_id=task_id,
                execution_id=execution_id,
                sandbox_id=sandbox_result.sandbox_id,
                output_dir=sandbox_result.output_dir,
                input_resource_ids=prepared.input_resource_ids,
            ).model_dump(mode="json"),
        )

        # Complete execution and emit event
        await ctx.step.run(
            "complete-and-emit",
            partial(
                _complete_and_emit,
                execution_id,
                run_id,
                experiment_id,
                task_id,
                prepared.task_name,
                prepared.parent_task_id,
                worker_result.output_text,
                persist_result.output_resource_ids,
                trace_context,
            ),
        )

        return TaskExecuteResult(
            run_id=run_id,
            task_id=task_id,
            execution_id=execution_id,
            success=True,
            outputs_count=persist_result.outputs_count,
            questions_asked=worker_result.questions_asked,
        )

    except Exception as exc:
        error_msg = str(exc)

        # Mark failed and emit event
        await ctx.step.run(
            "fail-and-emit",
            partial(
                _fail_and_emit,
                execution_id,
                run_id,
                experiment_id,
                task_id,
                prepared.task_name,
                prepared.parent_task_id,
                error_msg,
                trace_context,
            ),
        )

        raise inngest.NonRetriableError(f"Task execution failed: {error_msg}")


async def _emit_dashboard_task_running(
    run_id: UUID, task_id: UUID, task_name: str, parent_task_id: UUID | None
) -> None:
    """Emit dashboard task running event."""
    await dashboard_emitter.task_status_changed(
        run_id=run_id,
        task_id=task_id,
        task_name=task_name,
        old_status=TaskStatus.READY,
        new_status=TaskStatus.RUNNING,
        parent_task_id=parent_task_id,
        triggered_by=TaskTrigger.WORKER_STARTED,
    )


async def _complete_and_emit(
    execution_id: UUID,
    run_id: UUID,
    experiment_id: UUID,
    task_id: UUID,
    task_name: str,
    parent_task_id: UUID | None,
    output_text: str | None,
    output_resource_ids: list[UUID],
    trace_context: TraceContext,
) -> None:
    """Complete task execution, emit TaskCompletedEvent and dashboard event."""
    trace_sink = get_trace_sink()
    TaskExecutionService(trace_sink=trace_sink, trace_context=trace_context).finalize_success(
        FinalizeTaskExecutionCommand(
            execution_id=execution_id,
            output_text=output_text,
            output_resource_ids=output_resource_ids,
        )
    )
    event = TaskCompletedEvent(
        run_id=run_id,
        experiment_id=experiment_id,
        task_id=task_id,
        execution_id=execution_id,
    )
    await inngest_client.send(
        inngest.Event(name=TaskCompletedEvent.name, data=event.model_dump(mode="json"))
    )
    # Emit dashboard task completed event
    await dashboard_emitter.task_status_changed(
        run_id=run_id,
        task_id=task_id,
        task_name=task_name,
        old_status=TaskStatus.RUNNING,
        new_status=TaskStatus.COMPLETED,
        parent_task_id=parent_task_id,
        triggered_by=TaskTrigger.EXECUTION_SUCCEEDED,
    )
    execution = require_not_none(
        queries.task_executions.get(execution_id),
        f"TaskExecution {execution_id} not found",
    )
    trace_sink.emit_span(
        CompletedSpan(
            name="task.execute",
            context=trace_context,
            start_time=execution.started_at,
            end_time=execution.completed_at or utcnow(),
            attributes={
                "task_id": task_id,
                "execution_id": execution_id,
                "status": "completed",
                "output_resource_count": len(output_resource_ids),
            },
        )
    )


async def _fail_and_emit(
    execution_id: UUID,
    run_id: UUID,
    experiment_id: UUID,
    task_id: UUID,
    task_name: str,
    parent_task_id: UUID | None,
    error_msg: str,
    trace_context: TraceContext,
) -> None:
    """Mark task failed, emit TaskFailedEvent and dashboard event."""
    trace_sink = get_trace_sink()
    TaskExecutionService(trace_sink=trace_sink, trace_context=trace_context).finalize_failure(
        FailTaskExecutionCommand(
            execution_id=execution_id,
            run_id=run_id,
            task_id=task_id,
            error_message=error_msg,
        )
    )
    event = TaskFailedEvent(
        run_id=run_id,
        experiment_id=experiment_id,
        task_id=task_id,
        execution_id=execution_id,
        error=error_msg,
    )
    await inngest_client.send(
        inngest.Event(name=TaskFailedEvent.name, data=event.model_dump(mode="json"))
    )
    # Emit dashboard task failed event
    await dashboard_emitter.task_status_changed(
        run_id=run_id,
        task_id=task_id,
        task_name=task_name,
        old_status=TaskStatus.RUNNING,
        new_status=TaskStatus.FAILED,
        parent_task_id=parent_task_id,
        triggered_by=TaskTrigger.EXECUTION_FAILED,
    )
    execution = require_not_none(
        queries.task_executions.get(execution_id),
        f"TaskExecution {execution_id} not found",
    )
    trace_sink.emit_span(
        CompletedSpan(
            name="task.execute",
            context=trace_context,
            start_time=execution.started_at,
            end_time=execution.completed_at or utcnow(),
            attributes={
                "task_id": task_id,
                "execution_id": execution_id,
                "status": "failed",
                "error": error_msg,
            },
            status_code="error",
            status_message=error_msg,
        )
    )
