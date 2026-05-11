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

from ergon_core.api.benchmark import Task
from ergon_core.api.worker import WorkerContext, WorkerOutput, WorkerStreamItem
from ergon_core.core.application.graph.repository import WorkflowGraphRepository
from ergon_core.core.application.resources.repository import RunResourceRepository
from ergon_core.core.application.tasks.inspection import TaskInspectionService
from ergon_core.core.application.tasks.management import TaskManagementService
from ergon_core.core.infrastructure.dashboard.provider import get_dashboard_emitter
from ergon_core.core.domain.generation.context_parts import ContextPartChunk
from ergon_core.core.infrastructure.sandbox.lifecycle import SandboxLifecycleHub
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.application.context.events import ContextEventService
from ergon_core.core.infrastructure.inngest.errors import ContractViolationError
from ergon_core.core.application.jobs.models import WorkerExecuteJobRequest
from ergon_core.core.application.jobs.models import WorkerExecuteJobResult
from ergon_core.core.infrastructure.tracing import (
    CompletedSpan,
    get_trace_sink,
    worker_execute_context,
)

logger = logging.getLogger(__name__)
_SANDBOX_LIFECYCLE_HUB = SandboxLifecycleHub()


async def run_worker_execute_job(payload: WorkerExecuteJobRequest) -> WorkerExecuteJobResult:
    logger.info(
        "worker-execute run_id=%s task_id=%s",
        payload.run_id,
        payload.task_id,
    )
    span_start = datetime.now(UTC)

    with get_session() as session:
        try:
            node = WorkflowGraphRepository().node(
                session,
                run_id=payload.run_id,
                task_id=payload.task_id,
            )
        except Exception as exc:
            raise ContractViolationError(
                f"RunGraphNode task_id={payload.task_id} not found",
                run_id=payload.run_id,
                task_id=payload.task_id,
                execution_id=payload.execution_id,
                sandbox_id=payload.sandbox_id,
            ) from exc

    task = Task.from_definition(node.task_json, task_id=node.task_id)
    worker = task.worker

    worker_context = WorkerContext._for_job(
        run_id=payload.run_id,
        definition_id=payload.definition_id,
        execution_id=payload.execution_id,
        task_id=payload.task_id,
        task_mgmt=TaskManagementService(),
        task_inspect=TaskInspectionService(),
        resource_repo=RunResourceRepository(),
        session_factory=get_session,
    )

    context_event_repo = ContextEventService()
    dashboard_emitter = get_dashboard_emitter()
    context_event_repo.add_listener(dashboard_emitter.on_context_event)
    dashboard_emitter.register_execution(
        execution_id=payload.execution_id,
        task_node_id=payload.task_id,
    )

    chunk_count = 0
    try:
        sandbox = await _SANDBOX_LIFECYCLE_HUB.acquire(
            task.sandbox,
            run_id=payload.run_id,
            task_id=payload.task_id,
        )
        output, chunk_count = await _consume_worker_stream(
            worker.execute(task, context=worker_context, sandbox=sandbox),
            lambda chunk, count: _persist_context_events(
                context_event_repo,
                payload,
                chunk,
                count,
            ),
        )

    except Exception as exc:  # slopcop: ignore[no-broad-except]
        if "sandbox" in locals():
            try:
                await _SANDBOX_LIFECYCLE_HUB.release(sandbox)
            except Exception:  # slopcop: ignore[no-broad-except]
                logger.warning("failed to release sandbox after worker error", exc_info=True)
        error_msg = str(exc)
        logger.exception(
            "worker-execute failed task_id=%s after %d chunks: %s",
            payload.task_id,
            chunk_count,
            error_msg,
        )
        return WorkerExecuteJobResult(
            success=False,
            error=error_msg,
            sandbox_id=sandbox.sandbox_id if "sandbox" in locals() and sandbox.is_live else None,
            error_json={
                "message": error_msg,
                "exception_type": type(exc).__name__,
                "phase": "worker_execute",
                "stack": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
                "context": {},
            },
        )

    sink = get_trace_sink()
    sink.emit_span(
        CompletedSpan(
            name="worker.execute",
            context=worker_execute_context(
                payload.run_id,
                payload.task_id,
                payload.execution_id,
            ),
            start_time=span_start,
            end_time=datetime.now(UTC),
            attributes={
                "run_id": str(payload.run_id),
                "task_id": str(payload.task_id),
                "execution_id": str(payload.execution_id),
                "sandbox_id": payload.sandbox_id,
                "worker_type": worker.type_slug,
                "model_target": worker.model,
                "success": output.success,
                "output_length": len(output.output),
                "chunk_count": chunk_count,
            },
        )
    )

    return WorkerExecuteJobResult(
        success=output.success,
        final_assistant_message=output.output,
        error=None if output.success else output.output,
        sandbox_id=sandbox.sandbox_id if sandbox.is_live else None,
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
    payload: WorkerExecuteJobRequest,
    chunk: ContextPartChunk,
    chunk_count: int,
) -> None:
    """Persist one context chunk, swallowing failures so worker execution continues."""
    try:
        with get_session() as session:
            await context_event_repo.persist_chunk(
                session,
                run_id=payload.run_id,
                execution_id=payload.execution_id,
                worker_binding_key=payload.task_id.hex,
                chunk=chunk,
            )
    except Exception:  # slopcop: ignore[no-broad-except]
        logger.warning(
            "context event persist failed for execution %s chunk %d",
            payload.execution_id,
            chunk_count,
            exc_info=True,
        )
