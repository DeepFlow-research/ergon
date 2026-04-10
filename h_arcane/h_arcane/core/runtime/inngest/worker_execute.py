"""Inngest child function: worker execution.

Looks up the registered worker, constructs a BenchmarkTask, and runs execute().
Persists structured GenerationTurn records when the worker produces them.
Emits worker.execute span and post-hoc action spans from persisted RunActions.
"""

import logging
from datetime import UTC, datetime

import inngest
from arcane_builtins.registry import WORKERS
from h_arcane.api.results import WorkerResult
from h_arcane.api.task_types import BenchmarkTask
from h_arcane.api.worker_context import WorkerContext
from h_arcane.core.dashboard.event_contracts import DashboardGenerationTurnEvent
from h_arcane.core.persistence.shared.db import get_session
from h_arcane.core.persistence.telemetry.models import RunAction
from h_arcane.core.persistence.telemetry.repositories import GenerationTurnRepository
from h_arcane.core.providers.generation.pydantic_ai_format import extract_text, extract_tool_calls
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

    result = await worker.execute(task, context=worker_context)

    _persist_generation_turns(payload, result)
    await _emit_generation_turn_events(payload, result)

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
                "success": result.success,
                "output_length": len(result.output),
                "turn_count": len(result.turns),
            },
        )
    )

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


def _persist_generation_turns(payload: WorkerExecuteRequest, result: WorkerResult) -> None:
    """Persist ``WorkerResult.turns`` as ``RunGenerationTurn`` rows."""
    if not result.turns:
        return

    try:
        repo = GenerationTurnRepository()
        with get_session() as session:
            repo.persist_turns(
                session,
                run_id=payload.run_id,
                execution_id=payload.execution_id,
                worker_binding_key=payload.worker_binding_key,
                turns=result.turns,
            )
            session.commit()
        logger.info(
            "Persisted %d generation turns for execution_id=%s",
            len(result.turns),
            payload.execution_id,
        )
    except Exception:  # slopcop: ignore[no-broad-except]
        logger.warning("Failed to persist generation turns", exc_info=True)


async def _emit_generation_turn_events(payload: WorkerExecuteRequest, result: WorkerResult) -> None:
    """Emit dashboard events for each generation turn (live streaming)."""
    if not result.turns:
        return

    try:
        events: list[inngest.Event] = []
        for i, turn in enumerate(result.turns):
            response_text = extract_text(turn.raw_response)
            tool_calls = extract_tool_calls(turn.raw_response)

            evt = DashboardGenerationTurnEvent(
                run_id=payload.run_id,
                task_execution_id=payload.execution_id,
                worker_binding_key=payload.worker_binding_key,
                worker_name=payload.worker_type,
                turn_index=i,
                response_text=response_text,
                tool_calls=tool_calls,
                policy_version=turn.policy_version,
            )
            events.append(
                inngest.Event(
                    name=DashboardGenerationTurnEvent.name,
                    data=evt.model_dump(mode="json"),
                )
            )

        if events:
            await inngest_client.send(events)
    except Exception:  # slopcop: ignore[no-broad-except]
        logger.debug("Failed to emit generation turn dashboard events", exc_info=True)
