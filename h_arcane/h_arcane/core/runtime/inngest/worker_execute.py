"""Inngest child function: worker execution.

Looks up the registered worker, constructs a BenchmarkTask, and runs execute().
Emits worker.execute span and post-hoc action spans from persisted RunActions.
"""

import logging
from datetime import UTC, datetime

import inngest
from arcane_builtins.registry import WORKERS
from h_arcane.api.task_types import BenchmarkTask
from h_arcane.api.worker_context import WorkerContext
from h_arcane.core.persistence.shared.db import get_session
from h_arcane.core.persistence.telemetry.models import RunAction
from h_arcane.core.runtime.errors import RegistryLookupError
from h_arcane.core.runtime.inngest_client import inngest_client
from h_arcane.core.runtime.services.child_function_payloads import WorkerExecuteRequest
from h_arcane.core.runtime.services.inngest_function_results import WorkerExecuteResult
from h_arcane.core.runtime.tracing import (
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
    payload = WorkerExecuteRequest(**ctx.event.data)
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

    result = await worker.execute(task, context=worker_context)

    sink = get_trace_sink()
    sink.emit_span(CompletedSpan(
        name="worker.execute",
        context=worker_execute_context(
            payload.run_id, payload.task_id, payload.execution_id,
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
            "success": result.success,
            "output_length": len(result.output),
        },
    ))

    _emit_action_spans(sink, payload)

    return WorkerExecuteResult(
        success=True,
        output_text=result.output,
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

                sink.emit_span(CompletedSpan(
                    name=f"action.{a.action_type}",
                    context=action_context(
                        payload.run_id, payload.task_id,
                        payload.execution_id, a.id,
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
                ))
    except Exception:
        logger.debug("Could not emit action spans", exc_info=True)
