"""Inngest functions: cascade-cancel children when a parent reaches terminal.

Two functions: task/failed (block descendants) and task/cancelled (cancel
descendants). There is intentionally NO handler for task/completed — when a
manager task completes after spawning children, those children are not orphaned
and must continue running.

Each function uses two durable steps:
1. scan-and-cancel — queries children, writes CANCELLED via conditional guard,
   commits the transaction (step result is memoized, so retries skip this)
2. emit-cancelled-events — fans out task/cancelled for each transitioned child
"""

import logging
from uuid import UUID
import inngest

from ergon_core.core.application.tasks.management import TaskManagementService
from ergon_core.core.infrastructure.inngest.client import InngestEvent, inngest_client
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.application.events.task_events import (
    CancelCause,
    TaskCancelledEvent,
    TaskFailedEvent,
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
    svc = TaskManagementService()

    async def _scan_and_cancel() -> dict:
        with get_session() as session:
            result = await svc.cancel_orphans(
                session,
                run_id=run_id,
                definition_id=definition_id,
                parent_node_id=parent_node_id,
                cause=cause,
            )
            session.commit()
        return {
            "cancelled_node_ids": [str(nid) for nid in result.cancelled_node_ids],
            "events": [e.model_dump(mode="json") for e in result.events_to_emit],
        }

    scan_result = await ctx.step.run("scan-and-cancel", _scan_and_cancel)

    if scan_result["events"]:

        async def _emit_events() -> None:
            await inngest_client.send(
                [InngestEvent(name="task/cancelled", data=e) for e in scan_result["events"]]
            )

        await ctx.step.run("emit-cancelled-events", _emit_events)

    return len(scan_result["cancelled_node_ids"])


async def run_block_descendants_on_failed_job(
    ctx: inngest.Context, payload: TaskFailedEvent
) -> int:
    """When a parent fails, PENDING/READY containment descendants become BLOCKED.

    RUNNING descendants are not interrupted. Horizontal (edge-based) successor
    BLOCKED propagation is handled separately in propagation.py.
    """
    logger.info("block-descendants-on-failed parent=%s", payload.node_id)
    svc = TaskManagementService()

    async def _block_descendants() -> list[str]:
        with get_session() as session:
            blocked_ids = await svc.block_pending_descendants(
                session,
                run_id=payload.run_id,
                parent_node_id=payload.node_id,
                cause="parent_failed",
            )
            session.commit()
        return [str(nid) for nid in blocked_ids]

    blocked = await ctx.step.run("block-pending-descendants", _block_descendants)
    return len(blocked)


async def run_cancel_orphans_on_cancelled_job(
    ctx: inngest.Context, payload: TaskCancelledEvent
) -> int:
    logger.info("cancel-orphans parent=%s cause=parent_terminal", payload.node_id)
    return await _cancel_orphans_for(
        ctx,
        run_id=payload.run_id,
        definition_id=payload.definition_id,
        parent_node_id=payload.node_id,
        cause="parent_terminal",
    )
