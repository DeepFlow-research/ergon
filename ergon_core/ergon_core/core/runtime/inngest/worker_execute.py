"""Inngest child function: worker execution.

Looks up the registered worker, constructs a BenchmarkTask, and runs execute().
Consumes the async generator, persisting each yielded GenerationTurn to PG
via the repository. Dashboard events are emitted per-turn via the repository
listener pattern.
"""

import logging
from datetime import UTC, datetime

import inngest
from ergon_builtins.registry import WORKERS
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.worker_context import WorkerContext
from ergon_core.core.dashboard.emitter import dashboard_emitter
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunGenerationTurn
from ergon_core.core.persistence.telemetry.repositories import GenerationTurnRepository
from ergon_core.core.runtime.errors import RegistryLookupError
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.runtime.services.child_function_payloads import WorkerExecuteRequest
from ergon_core.core.runtime.services.inngest_function_results import WorkerExecuteResult
from ergon_core.core.runtime.tracing import (
    CompletedSpan,
    get_trace_sink,
    worker_execute_context,
)
from sqlmodel import select

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

    repo = GenerationTurnRepository()
    repo.add_listener(dashboard_emitter.on_turn_persisted)

    turn_count = 0
    try:
        turn_start = datetime.now(UTC)
        async for turn in worker.execute(task, context=worker_context):
            turn_end = datetime.now(UTC)
            turn = turn.model_copy(update={
                "started_at": turn.started_at or turn_start,
                "completed_at": turn.completed_at or turn_end,
            })
            with get_session() as session:
                await repo.persist_single(
                    session,
                    run_id=payload.run_id,
                    execution_id=payload.execution_id,
                    worker_binding_key=payload.worker_binding_key,
                    turn=turn,
                    turn_index=turn_count,
                    execution_outcome="success",
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
        with get_session() as session:
            repo.mark_execution_outcome(session, payload.execution_id, "failure")
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

    _emit_tool_call_spans(sink, payload)

    return WorkerExecuteResult(
        success=True,
        output_text=output.output,
    )


def _emit_tool_call_spans(sink, payload: WorkerExecuteRequest) -> None:
    """Emit OTEL spans for tool calls extracted from generation turns."""
    try:
        with get_session() as session:
            turns = list(
                session.exec(
                    select(RunGenerationTurn)
                    .where(
                        RunGenerationTurn.run_id == payload.run_id,
                        RunGenerationTurn.task_execution_id == payload.execution_id,
                    )
                    .order_by(RunGenerationTurn.turn_index)
                ).all()
            )

            span_num = 0
            for turn in turns:
                tool_calls = turn.parsed_tool_calls()
                results_by_id = {
                    tr.tool_call_id: tr for tr in turn.parsed_tool_results()
                }
                for tc in tool_calls:
                    result = results_by_id.get(tc.tool_call_id)
                    sink.emit_span(
                        CompletedSpan(
                            name=f"tool.{tc.tool_name}",
                            context=worker_execute_context(
                                payload.run_id,
                                payload.task_id,
                                payload.execution_id,
                            ),
                            start_time=turn.started_at or turn.created_at,
                            end_time=turn.completed_at or turn.created_at,
                            attributes={
                                "run_id": str(payload.run_id),
                                "task_id": str(payload.task_id),
                                "execution_id": str(payload.execution_id),
                                "turn_index": turn.turn_index,
                                "tool_name": tc.tool_name,
                                "tool_call_id": tc.tool_call_id,
                                "has_result": result is not None,
                            },
                        )
                    )
                    span_num += 1
    except Exception:  # slopcop: ignore[no-broad-except]
        logger.debug("Could not emit tool call spans", exc_info=True)
