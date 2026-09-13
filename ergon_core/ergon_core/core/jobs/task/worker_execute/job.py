"""Inngest child function: worker execution.

Looks up the registered worker, constructs a Task, and runs execute().
Consumes the async generator, persisting context events to PG via the
ContextEventService. Dashboard events are emitted per chunk via the
repository listener pattern.
"""

import logging
import traceback
from collections.abc import AsyncIterable, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from ergon_core.api.task import Task
from ergon_core.api.worker import WorkerContext, WorkerOutput, WorkerStreamItem
from ergon_core.api.worker.results import SpawnedTaskHandle
from ergon_core.core.jobs._events import send_job_step_event
from ergon_core.core.jobs.task.execute.contract import TaskReadyEvent
from ergon_core.core.application.events.service import get_dashboard_event_publisher
from ergon_core.core.application.resources.service import SampleResourceReadService
from ergon_core.core.application.runtime.task_execution import TaskExecutionService
from ergon_core.core.application.runtime.task_inspection import TaskInspectionService
from ergon_core.core.application.runtime.task_management import TaskManagementService
from ergon_core.core.application.runtime.task_models import (
    CancelTaskCommand,
    CancelTaskResult,
    RefineTaskCommand,
    RefineTaskResult,
    RestartTaskCommand,
    RestartTaskResult,
)
from ergon_core.core.shared.context_parts import ContextPartChunk
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.application.context.service import ContextEventService, ContextReplayMismatch
from ergon_core.core.infrastructure.inngest.errors import ContractViolationError
from ergon_core.core.persistence.context.models import SampleContextEvent
from .composition import worker_checkpoint_store
from .contract import WorkerExecuteRequest
from .contract import WorkerExecuteResult
from ergon_core.core.infrastructure.tracing import (
    CompletedSpan,
    get_trace_sink,
    worker_execute_context,
)
from ergon_core.core.persistence.context.models import SampleContextEvent
from ergon_core.core.views.dashboard_events.context_events import context_event_to_dashboard_event
from pydantic import BaseModel, Field
from ergon_core.core.application.runtime.errors import GraphError
from ergon_core.core.application.runtime.task_errors import (
    TaskRunningError,
    TaskAlreadyTerminalError,
    TaskNotTerminalError,
)
from sqlmodel import Session

logger = logging.getLogger(__name__)


async def run_worker_execute_job(
    payload: WorkerExecuteRequest,
    *,
    ctx: object | None = None,
) -> WorkerExecuteResult:
    logger.info(
        "worker-execute sample_id=%s task_id=%s worker_type=%s",
        payload.sample_id,
        payload.task_id,
        payload.worker_type,
    )
    span_start = datetime.now(UTC)

    # Read the typed run-tier view instead of rebuilding Task
    # from definition rows. No definition-tier repository, no component
    # catalog, no raw graph row read in this job — all of that lives
    # behind TaskExecutionService.
    task_execution = TaskExecutionService()
    with get_session() as session:
        view = await task_execution.load_task_view(
            session,
            sample_id=payload.sample_id,
            task_id=payload.task_id,
            sandbox_id=payload.sandbox_id,
        )
    task = view.task

    worker = task.worker
    if not task.sandbox.is_live:
        raise ContractViolationError(
            "worker-execute object-bound task requires a live sandbox attached via sandbox_id",
            sample_id=payload.sample_id,
            task_id=payload.task_id,
            execution_id=payload.execution_id,
            sandbox_id=payload.sandbox_id,
        )
    worker.validate_runtime_deps()

    # Cancellation needs the live sandbox identity while the worker is running,
    # including when inference fails or a durable wait never produces output.
    with get_session() as session:
        await task_execution.attach_sandbox_to_execution(
            session, execution_id=payload.execution_id, sandbox_id=payload.sandbox_id
        )
        session.commit()

    worker_context = WorkerContext._for_job(
        sample_id=payload.sample_id,
        task_id=payload.task_id,
        execution_id=payload.execution_id,
        sandbox_id=payload.sandbox_id,
        task_mgmt=_task_management_service_for_context(ctx),
        task_inspect=TaskInspectionService(),
        resource_service=SampleResourceReadService(),
        session_factory=get_session,
        steps=None if ctx is None else cast(Any, ctx).step,
        checkpoint_store=worker_checkpoint_store(task.sandbox, payload),
    )

    context_event_repo = ContextEventService()
    dashboard_publisher = get_dashboard_event_publisher()
    execution_task_map = {payload.execution_id: payload.task_id}

    async def _publish_context_event(event: SampleContextEvent) -> None:
        dashboard_event = context_event_to_dashboard_event(event, execution_task_map)
        if dashboard_event is None:
            logger.warning(
                "context_event: no task_id for execution %s",
                event.task_attempt_id,
            )
            return
        await dashboard_publisher.publish(dashboard_event)

    context_event_repo.add_listener(_publish_context_event)

    chunk_count = 0
    try:
        output, chunk_count = await _consume_worker_stream(
            cast(AsyncIterable[WorkerStreamItem], worker.execute(task, context=worker_context)),
            lambda chunk, count: _persist_context_events(
                context_event_repo,
                payload,
                chunk,
                count,
            ),
        )

    except Exception as exc:  # slopcop: ignore[no-broad-except]
        error_msg = str(exc)
        logger.exception(
            "worker-execute failed task_id=%s after %d chunks: %s",
            payload.task_id,
            chunk_count,
            error_msg,
        )
        return WorkerExecuteResult(
            success=False,
            error=error_msg,
            error_json={
                "message": error_msg,
                "exception_type": type(exc).__name__,
                "phase": "worker_execute",
                "stack": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
                "context": {},
            },
        )

    # Persist worker output BEFORE returning to the
    # orchestrator. The orchestrator's next step is the per-evaluator
    # fanout (`execute_task._fan_out_evaluators`); each eval worker
    # receives only a thin `TaskEvaluateRequest` and reloads everything
    # else from the run-tier read boundary:
    #
    #   WorkerOutput      ← TaskExecutionService.load_worker_output(execution_id)
    #   live sandbox_id   ← session.get(SampleTaskAttempt, ...).sandbox_id
    #                       (then fed to load_task_view(..., sandbox_id=))
    #
    # The sandbox identity was committed before executing the worker. Output
    # must also commit before the evaluator fanout reads this attempt.
    with get_session() as session:
        await task_execution.persist_worker_output(
            session,
            execution_id=payload.execution_id,
            output=output,
        )
        session.commit()

    sink = get_trace_sink()
    sink.emit_span(
        CompletedSpan(
            name="worker.execute",
            context=worker_execute_context(
                payload.sample_id,
                payload.task_id,
                payload.execution_id,
            ),
            start_time=span_start,
            end_time=datetime.now(UTC),
            attributes={
                "sample_id": str(payload.sample_id),
                "task_id": str(payload.task_id),
                "execution_id": str(payload.execution_id),
                "sandbox_id": payload.sandbox_id,
                "worker_type": payload.worker_type,
                "model_target": payload.model_target,
                "success": output.success,
                "output_length": len(output.output),
                "chunk_count": chunk_count,
            },
        )
    )

    return WorkerExecuteResult(
        success=output.success,
        final_assistant_message=output.output,
        error=None if output.success else output.output,
    )


def _task_management_service_for_context(ctx: Any | None) -> TaskManagementService:
    if ctx is None:
        return TaskManagementService()
    return _StepAwareTaskManagementService(ctx)


class _ReadyDispatch(BaseModel):
    model_config = {"frozen": True}

    sample_id: UUID
    task_id: UUID


class _SpawnTaskStepResult(BaseModel):
    model_config = {"frozen": True}

    handle: SpawnedTaskHandle
    ready: list[_ReadyDispatch]


class _MutationRejection(BaseModel):
    kind: str
    message: str
    task_id: UUID | None = None
    current_status: str | None = None

    def raise_error(self) -> None:
        status_errors = {
            "TaskRunningError": TaskRunningError,
            "TaskAlreadyTerminalError": TaskAlreadyTerminalError,
            "TaskNotTerminalError": TaskNotTerminalError,
        }
        if (
            self.kind in status_errors
            and self.task_id is not None
            and self.current_status is not None
        ):
            raise status_errors[self.kind](self.task_id, self.current_status)
        if self.kind == "ValueError":
            raise ValueError(self.message)
        raise GraphError(self.message)


class _MutationStepResult(BaseModel):
    result: CancelTaskResult | RefineTaskResult | RestartTaskResult | None = None
    ready: list[_ReadyDispatch] = Field(default_factory=list)
    rejection: _MutationRejection | None = None


class _StepAwareTaskManagementService(TaskManagementService):
    """Task management facade for workers running inside an Inngest function.

    Worker-authored graph mutations must be memoized as Inngest steps before
    any child task/ready events are emitted. Otherwise ``ctx.step.send_event``
    interrupts and replays the worker function, re-running the DB mutation.
    """

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx
        self._spawn_task_call_index = 0
        self._mutation_call_index = 0
        self._active_ready_dispatches: list[_ReadyDispatch] | None = None
        super().__init__(task_ready_dispatcher=self._collect_ready_dispatch)

    async def spawn_dynamic_task(
        self,
        *,
        sample_id: UUID,
        parent_task_id: UUID,
        task: Task,
        depends_on: tuple[UUID, ...] = (),
    ) -> SpawnedTaskHandle:
        call_index = self._spawn_task_call_index
        self._spawn_task_call_index += 1
        step_id = f"spawn-task-{parent_task_id}-{call_index}"

        async def _run_spawn() -> _SpawnTaskStepResult:
            previous = self._active_ready_dispatches
            ready: list[_ReadyDispatch] = []
            self._active_ready_dispatches = ready
            try:
                handle = await TaskManagementService.spawn_dynamic_task(
                    self,
                    sample_id=sample_id,
                    parent_task_id=parent_task_id,
                    task=task,
                    depends_on=depends_on,
                )
            finally:
                self._active_ready_dispatches = previous
            return _SpawnTaskStepResult(handle=handle, ready=ready)

        spawned = await self._ctx.step.run(
            step_id,
            _run_spawn,
            output_type=_SpawnTaskStepResult,
        )
        await self._dispatch_collected_ready_events(step_id, spawned.ready)
        return spawned.handle

    async def _memoized_mutation(
        self,
        name: str,
        operation: Callable[[], Awaitable[CancelTaskResult | RefineTaskResult | RestartTaskResult]],
    ) -> _MutationStepResult:
        index = self._mutation_call_index
        self._mutation_call_index += 1
        step_id = f"{name}-{index}"

        async def mutate() -> _MutationStepResult:
            previous = self._active_ready_dispatches
            ready: list[_ReadyDispatch] = []
            self._active_ready_dispatches = ready
            try:
                result = await operation()
            except (GraphError, ValueError) as error:
                rejection = _MutationRejection(kind=type(error).__name__, message=str(error))
                if isinstance(
                    error, (TaskRunningError, TaskAlreadyTerminalError, TaskNotTerminalError)
                ):
                    rejection.task_id = error.task_id
                    rejection.current_status = error.current_status
                return _MutationStepResult(rejection=rejection)
            finally:
                self._active_ready_dispatches = previous
            return _MutationStepResult(result=result, ready=ready)

        saved = await self._ctx.step.run(step_id, mutate, output_type=_MutationStepResult)
        if saved.rejection is not None:
            saved.rejection.raise_error()
        await self._dispatch_collected_ready_events(step_id, saved.ready)
        return saved

    async def refine_task(self, session: Session, command: RefineTaskCommand) -> RefineTaskResult:
        async def mutate() -> RefineTaskResult:
            return await super(_StepAwareTaskManagementService, self).refine_task(session, command)

        saved = await self._memoized_mutation(f"refine-{command.task_id}", mutate)
        return cast(RefineTaskResult, saved.result)

    async def cancel_task(self, session: Session, command: CancelTaskCommand) -> CancelTaskResult:
        async def mutate() -> CancelTaskResult:
            return await super(_StepAwareTaskManagementService, self).cancel_task(session, command)

        saved = await self._memoized_mutation(f"cancel-{command.task_id}", mutate)
        return cast(CancelTaskResult, saved.result)

    async def restart_task(
        self, session: Session, command: RestartTaskCommand
    ) -> RestartTaskResult:
        async def mutate() -> RestartTaskResult:
            return await super(_StepAwareTaskManagementService, self).restart_task(session, command)

        saved = await self._memoized_mutation(f"restart-{command.task_id}", mutate)
        return cast(RestartTaskResult, saved.result)

    async def _collect_ready_dispatch(
        self,
        sample_id: UUID,
        task_id: UUID,
    ) -> None:
        if self._active_ready_dispatches is None:
            raise ContractViolationError(
                "Worker task-ready dispatch attempted outside a memoized graph mutation",
                sample_id=sample_id,
                task_id=task_id,
            )
        self._active_ready_dispatches.append(_ReadyDispatch(sample_id=sample_id, task_id=task_id))

    async def _dispatch_collected_ready_events(
        self,
        parent_step_id: str,
        ready: list[_ReadyDispatch],
    ) -> None:
        for dispatch in ready:
            event = TaskReadyEvent(
                sample_id=dispatch.sample_id,
                task_id=dispatch.task_id,
            )
            await send_job_step_event(
                self._ctx,
                f"{parent_step_id}-dispatch-task-ready-{dispatch.task_id}",
                TaskReadyEvent.name,
                event.model_dump(mode="json"),
            )


async def _consume_worker_stream(
    stream: AsyncIterable[WorkerStreamItem],
    persist_chunk: Callable[[ContextPartChunk, int], Awaitable[None]],
) -> tuple[WorkerOutput, int]:
    """Persist context chunks and return the terminal worker output."""
    output: WorkerOutput | None = None
    chunk_count = 0

    async for item in stream:
        if isinstance(item, WorkerOutput):
            if output is not None:
                raise ContractViolationError("Worker emitted multiple terminal WorkerOutput items")
            output = item
            continue

        if output is not None:
            raise ContractViolationError("Worker emitted context chunk after terminal WorkerOutput")

        if not isinstance(item, ContextPartChunk):
            raise ContractViolationError(
                f"Worker stream expected ContextPartChunk or WorkerOutput, got {type(item).__name__}"
            )

        await persist_chunk(item, chunk_count)
        chunk_count += 1

    if output is None:
        raise ContractViolationError("Worker stream ended without terminal WorkerOutput")

    return output, chunk_count


async def _persist_context_events(
    context_event_repo: ContextEventService,
    payload: WorkerExecuteRequest,
    chunk: ContextPartChunk,
    chunk_count: int,
) -> None:
    """Persist one context chunk, swallowing failures so worker execution continues."""
    try:
        with get_session() as session:
            await context_event_repo.persist_chunk(
                session,
                sample_id=payload.sample_id,
                execution_id=payload.execution_id,
                worker_binding_key=payload.assigned_worker_slug,
                chunk=chunk,
                replay=True,
            )
    except ContextReplayMismatch:
        raise
    except Exception:  # slopcop: ignore[no-broad-except]
        logger.warning(
            "context event persist failed for execution %s chunk %d",
            payload.execution_id,
            chunk_count,
            exc_info=True,
        )
