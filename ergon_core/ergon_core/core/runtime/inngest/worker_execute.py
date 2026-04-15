"""Inngest child function: worker execution.

Looks up the registered worker, constructs a BenchmarkTask, and runs execute().
Consumes the async generator, persisting context events to PG via the
ContextEventRepository. Dashboard events are emitted per-turn via the
repository listener pattern.
"""

import logging
from datetime import UTC, datetime

import inngest
from ergon_builtins.registry import WORKERS
from ergon_core.api.generation import GenerationTurn
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.worker_context import WorkerContext
from ergon_core.core.dashboard.emitter import dashboard_emitter
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.context.repository import ContextEventRepository
from ergon_core.core.runtime.errors import RegistryLookupError
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.runtime.services.child_function_payloads import WorkerExecuteRequest
from ergon_core.core.runtime.services.inngest_function_results import WorkerExecuteResult
from ergon_core.core.runtime.tracing import (
    CompletedSpan,
    get_trace_sink,
    worker_execute_context,
)

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
        name=payload.worker_binding_key,
        model=payload.model_target,
    )

    task = BenchmarkTask(
        task_key=payload.task_key,
        instance_key=str(payload.execution_id),
        description=payload.task_description,
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
    context_event_repo.add_listener(dashboard_emitter.on_context_event)
    dashboard_emitter.register_execution(
        execution_id=payload.execution_id,
        task_node_id=payload.node_id,
    )

    turn_count = 0
    try:
        turn_start = datetime.now(UTC)
        async for turn in worker.execute(task, context=worker_context):
            turn_end = datetime.now(UTC)
            turn = turn.model_copy(
                update={
                    "started_at": turn.started_at or turn_start,
                    "completed_at": turn.completed_at or turn_end,
                }
            )
            await _persist_context_events(
                context_event_repo,
                payload,
                turn,
                turn_count,
            )
            turn_count += 1
            turn_start = datetime.now(UTC)

        output = worker.get_output(worker_context)

    except Exception as exc:  # slopcop: ignore[no-broad-except]
        error_msg = str(exc)
        logger.exception(
            "worker-execute failed task_id=%s after %d turns: %s",
            payload.task_id,
            turn_count,
            error_msg,
        )
        raise

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
                "turn_count": turn_count,
            },
        )
    )

    return WorkerExecuteResult(
        success=True,
        output_text=output.output,
    )


async def _persist_context_events(
    context_event_repo: ContextEventRepository,
    payload: WorkerExecuteRequest,
    turn: GenerationTurn,
    turn_count: int,
) -> None:
    """Persist context events for a single turn, swallowing failures so they
    never interrupt the primary generation turn write."""
    try:
        with get_session() as session:
            await context_event_repo.persist_turn(
                session,
                run_id=payload.run_id,
                execution_id=payload.execution_id,
                worker_binding_key=payload.worker_binding_key,
                turn=turn,
            )
    except Exception:  # slopcop: ignore[no-broad-except]
        logger.warning(
            "context event persist failed for execution %s turn %d",
            payload.execution_id,
            turn_count,
            exc_info=True,
        )
