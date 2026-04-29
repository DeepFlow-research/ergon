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

from ergon_core.api.benchmark import EmptyTaskPayload, Task
from ergon_core.api.registry import registry
from ergon_core.api.worker import WorkerContext, WorkerOutput, WorkerStreamItem
from ergon_core.core.application.experiments.repository import DefinitionRepository
from ergon_core.core.infrastructure.dashboard.provider import get_dashboard_emitter
from ergon_core.core.domain.generation.context_parts import ContextPartChunk
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.application.context.events import ContextEventService
from ergon_core.core.infrastructure.inngest.errors import ContractViolationError, RegistryLookupError
from ergon_core.core.application.jobs.models import WorkerExecuteJobRequest
from ergon_core.core.application.jobs.models import WorkerExecuteJobResult
from ergon_core.core.infrastructure.tracing import (
    CompletedSpan,
    get_trace_sink,
    worker_execute_context,
)
from pydantic import BaseModel

logger = logging.getLogger(__name__)


async def run_worker_execute_job(payload: WorkerExecuteJobRequest) -> WorkerExecuteJobResult:
    logger.info(
        "worker-execute run_id=%s task_id=%s worker_type=%s",
        payload.run_id,
        payload.task_id,
        payload.worker_type,
    )
    span_start = datetime.now(UTC)

    worker_cls = registry.workers.get(payload.worker_type)
    if worker_cls is None:
        raise RegistryLookupError(
            registry_name="worker",
            slug=payload.worker_type,
            run_id=payload.run_id,
            task_id=payload.task_id,
            execution_id=payload.execution_id,
            sandbox_id=payload.sandbox_id,
        )

    worker = worker_cls(
        name=payload.assigned_worker_slug,
        model=payload.model_target,
        task_id=payload.task_id,
        sandbox_id=payload.sandbox_id,
    )

    task_payload = None
    instance_key = str(payload.execution_id)
    if payload.task_id is not None:
        with get_session() as session:
            task_row, instance_row = DefinitionRepository().task_with_instance(
                session,
                payload.task_id,
            )
        benchmark_cls = registry.benchmarks.get(payload.benchmark_type)
        if benchmark_cls is not None:
            task_payload = task_row.task_payload_as(benchmark_cls.task_payload_model)
        instance_key = instance_row.instance_key

    task = Task[BaseModel](
        task_slug=payload.task_slug,
        instance_key=instance_key,
        description=payload.task_description,
        task_payload=task_payload or EmptyTaskPayload(),
    )

    worker_context = WorkerContext(
        run_id=payload.run_id,
        definition_id=payload.definition_id,
        task_id=payload.task_id,
        execution_id=payload.execution_id,
        sandbox_id=payload.sandbox_id,
        node_id=payload.node_id,
    )

    context_event_repo = ContextEventService()
    dashboard_emitter = get_dashboard_emitter()
    context_event_repo.add_listener(dashboard_emitter.on_context_event)
    dashboard_emitter.register_execution(
        execution_id=payload.execution_id,
        task_node_id=payload.node_id,
    )

    chunk_count = 0
    try:
        output, chunk_count = await _consume_worker_stream(
            worker.execute(task, context=worker_context),
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
        return WorkerExecuteJobResult(
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
                "worker_type": payload.worker_type,
                "model_target": payload.model_target,
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
                worker_binding_key=payload.assigned_worker_slug,
                chunk=chunk,
            )
    except Exception:  # slopcop: ignore[no-broad-except]
        logger.warning(
            "context event persist failed for execution %s chunk %d",
            payload.execution_id,
            chunk_count,
            exc_info=True,
        )
