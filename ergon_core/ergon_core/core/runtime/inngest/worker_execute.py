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
from ergon_core.core.persistence.telemetry.models import RunAction
from ergon_core.core.persistence.telemetry.repositories import GenerationTurnRepository
from ergon_core.core.runtime.errors import RegistryLookupError
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.runtime.services.child_function_payloads import WorkerExecuteRequest
from ergon_core.core.runtime.services.inngest_function_results import WorkerExecuteResult
from ergon_core.core.runtime.tracing import (
    CompletedSpan,
    action_context,
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
        task_id=payload.task_id,
        execution_id=payload.execution_id,
        sandbox_id=payload.sandbox_id,
    )

    repo = GenerationTurnRepository()
    repo.add_listener(dashboard_emitter.on_turn_persisted)

    turn_count = 0
    try:
        async for turn in worker.execute(task, context=worker_context):
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

    _emit_action_spans(sink, payload)

    return WorkerExecuteResult(
        success=True,
        output_text=output.output,
    )


def _emit_action_spans(sink, payload: WorkerExecuteRequest) -> None:
    """Emit post-hoc action spans from persisted RunAction rows."""
    try:
        with get_session() as session:
            actions = list(
                session.exec(
                    select(RunAction)
                    .where(
                        RunAction.run_id == payload.run_id,
                        RunAction.task_execution_id == payload.execution_id,
                    )
                    .order_by(RunAction.action_num)
                ).all()
            )
            for a in actions:
                duration_ms = None
                if a.started_at and a.completed_at:
                    duration_ms = int((a.completed_at - a.started_at).total_seconds() * 1000)

                sink.emit_span(
                    CompletedSpan(
                        name=f"action.{a.action_type}",
                        context=action_context(
                            payload.run_id,
                            payload.task_id,
                            payload.execution_id,
                            a.id,
                        ),
                        start_time=a.started_at or datetime.now(UTC),
                        end_time=a.completed_at or datetime.now(UTC),
                        attributes={
                            "run_id": str(payload.run_id),
                            "task_id": str(payload.task_id),
                            "execution_id": str(payload.execution_id),
                            "action_id": str(a.id),
                            "action_num": a.action_num,
                            "action_type": a.action_type,
                            "success": a.error_json is None,
                            "duration_ms": duration_ms,
                        },
                    )
                )
    except Exception:  # slopcop: ignore[no-broad-except]
        logger.debug("Could not emit action spans", exc_info=True)
