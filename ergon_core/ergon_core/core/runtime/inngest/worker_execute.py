"""Inngest child function: worker execution.

Looks up the registered worker, constructs a BenchmarkTask, and runs execute().
Consumes the async generator, persisting context events to PG via the
ContextEventRepository. Dashboard events are emitted per chunk via the
repository listener pattern.
"""

import logging
import traceback
from datetime import UTC, datetime

import inngest
from ergon_builtins.registry import BENCHMARKS, WORKERS
from ergon_core.api.task_types import BenchmarkTask, EmptyTaskPayload
from ergon_core.api.worker_context import WorkerContext
from ergon_core.core.dashboard.provider import get_dashboard_emitter
from ergon_core.core.generation import ContextPartChunk
from ergon_core.core.persistence.context.repository import ContextEventRepository
from ergon_core.core.persistence.queries import queries
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.runtime.errors import RegistryLookupError
from ergon_core.core.runtime.inngest.client import inngest_client
from ergon_core.core.runtime.services.child_function_payloads import WorkerExecuteRequest
from ergon_core.core.runtime.services.inngest_function_results import WorkerExecuteResult
from ergon_core.core.runtime.tracing import (
    CompletedSpan,
    get_trace_sink,
    worker_execute_context,
)
from pydantic import BaseModel

logger = logging.getLogger(__name__)


@inngest_client.create_function(
    fn_id="worker-execute",
    trigger=inngest.TriggerEvent(event="task/worker-execute"),
    retries=0,
    output_type=WorkerExecuteResult,
)
async def worker_execute_fn(ctx: inngest.Context) -> WorkerExecuteResult:
    payload = WorkerExecuteRequest.model_validate(ctx.event.data)
    logger.info(
        "worker-execute run_id=%s task_id=%s worker_type=%s",
        payload.run_id,
        payload.task_id,
        payload.worker_type,
    )
    span_start = datetime.now(UTC)

    worker_cls = WORKERS.get(payload.worker_type)
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
        task_row, instance_row = queries.definitions.get_task_with_instance(payload.task_id)
        benchmark_cls = BENCHMARKS.get(payload.benchmark_type)
        if benchmark_cls is not None:
            task_payload = task_row.task_payload_as(benchmark_cls.task_payload_model)
        instance_key = instance_row.instance_key

    task = BenchmarkTask[BaseModel](
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

    context_event_repo = ContextEventRepository()
    dashboard_emitter = get_dashboard_emitter()
    context_event_repo.add_listener(dashboard_emitter.on_context_event)
    dashboard_emitter.register_execution(
        execution_id=payload.execution_id,
        task_node_id=payload.node_id,
    )

    chunk_count = 0
    try:
        async for chunk in worker.execute(task, context=worker_context):
            await _persist_context_events(
                context_event_repo,
                payload,
                chunk,
                chunk_count,
            )
            chunk_count += 1

        output = worker.get_output(worker_context)

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

    return WorkerExecuteResult(
        success=output.success,
        final_assistant_message=output.output,
        error=None if output.success else output.output,
    )


async def _persist_context_events(
    context_event_repo: ContextEventRepository,
    payload: WorkerExecuteRequest,
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
