"""Inngest functions: cascade-cancel children when a parent reaches terminal.

Three functions, one per trigger event (task/completed, task/failed,
task/cancelled). Keeping them separate sidesteps SDK version skew on
multi-trigger syntax and makes the Inngest dashboard self-explanatory.

Each function uses two durable steps:
1. scan-and-cancel — queries children, writes CANCELLED via conditional guard
2. emit-cancelled-events — fans out task/cancelled for each transitioned child

Splitting ensures the DB commit is memoized; retries skip step 1 if it
already succeeded.
"""

import logging
from uuid import UUID

import inngest

from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.runtime.events.task_events import (
    CancelCause,
    TaskCancelledEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
)
from ergon_core.core.runtime.inngest_client import RUN_CANCEL, inngest_client
from ergon_core.core.runtime.services.subtask_blocking_service import SubtaskBlockingService
from ergon_core.core.runtime.services.subtask_cancellation_service import (
    SubtaskCancellationService,
)

logger = logging.getLogger(__name__)


async def _cancel_orphans_for(
    ctx: inngest.Context,
    *,
    run_id: UUID,
    definition_id: UUID,
    parent_node_id: UUID,
    cause: CancelCause,
) -> int:
    """Two durable steps: scan-and-cancel, then emit events."""
    svc = SubtaskCancellationService()

    async def _scan_and_cancel() -> dict:
        with get_session() as session:
            result = await svc.cancel_orphans(
                session,
                run_id=run_id,
                definition_id=definition_id,
                parent_node_id=parent_node_id,
                cause=cause,
            )
        return {
            "cancelled_node_ids": [str(nid) for nid in result.cancelled_node_ids],
            "events": [e.model_dump(mode="json") for e in result.events_to_emit],
        }

    scan_result = await ctx.step.run("scan-and-cancel", _scan_and_cancel)

    if scan_result["events"]:

        async def _emit_events() -> None:
            await inngest_client.send(
                [inngest.Event(name="task/cancelled", data=e) for e in scan_result["events"]]
            )

        await ctx.step.run("emit-cancelled-events", _emit_events)

    return len(scan_result["cancelled_node_ids"])


@inngest_client.create_function(
    fn_id="cancel-orphans-on-completed",
    trigger=inngest.TriggerEvent(event="task/completed"),
    cancel=RUN_CANCEL,
    retries=1,
)
async def cancel_orphans_on_completed_fn(ctx: inngest.Context) -> int:
    payload = TaskCompletedEvent.model_validate(ctx.event.data)
    logger.info("cancel-orphans parent=%s cause=parent_terminal", payload.node_id)
    return await _cancel_orphans_for(
        ctx,
        run_id=payload.run_id,
        definition_id=payload.definition_id,
        parent_node_id=payload.node_id,
        cause="parent_terminal",
    )


@inngest_client.create_function(
    fn_id="block-descendants-on-failed",
    trigger=inngest.TriggerEvent(event="task/failed"),
    cancel=RUN_CANCEL,
    retries=1,
)
async def block_descendants_on_failed_fn(ctx: inngest.Context) -> int:
    """When a parent fails, PENDING/READY containment descendants become BLOCKED.

    RUNNING descendants are not interrupted. Horizontal (edge-based) successor
    BLOCKED propagation is handled separately in propagation.py.
    """
    payload = TaskFailedEvent.model_validate(ctx.event.data)
    logger.info("block-descendants-on-failed parent=%s", payload.node_id)
    svc = SubtaskBlockingService()

    async def _block_descendants() -> list[str]:
        with get_session() as session:
            blocked_ids = await svc.block_pending_descendants(
                session,
                run_id=payload.run_id,
                parent_node_id=payload.node_id,
                cause="parent_failed",
            )
        return [str(nid) for nid in blocked_ids]

    blocked = await ctx.step.run("block-pending-descendants", _block_descendants)
    return len(blocked)


@inngest_client.create_function(
    fn_id="cancel-orphans-on-cancelled",
    trigger=inngest.TriggerEvent(event="task/cancelled"),
    cancel=RUN_CANCEL,
    retries=1,
)
async def cancel_orphans_on_cancelled_fn(ctx: inngest.Context) -> int:
    payload = TaskCancelledEvent.model_validate(ctx.event.data)
    logger.info("cancel-orphans parent=%s cause=parent_terminal", payload.node_id)
    return await _cancel_orphans_for(
        ctx,
        run_id=payload.run_id,
        definition_id=payload.definition_id,
        parent_node_id=payload.node_id,
        cause="parent_terminal",
    )
