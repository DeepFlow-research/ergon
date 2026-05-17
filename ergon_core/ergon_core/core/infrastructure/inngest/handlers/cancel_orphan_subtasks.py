"""Inngest adapters for descendant cancellation."""

# TODO: when I said that jobs should die, each of these handles should probably become a module which owns its own logic and contracts? and maybe deserves some domain consolidation also
import inngest

from ergon_core.core.application.jobs.cancel_orphan_subtasks import (
    run_block_descendants_on_failed_job,
    run_cancel_orphans_on_cancelled_job,
)
from ergon_core.core.infrastructure.inngest.client import RUN_CANCEL, inngest_client
from ergon_core.core.application.events.task_events import TaskCancelledEvent, TaskFailedEvent


@inngest_client.create_function(
    fn_id="block-descendants-on-failed",
    trigger=inngest.TriggerEvent(event="task/failed"),
    cancel=RUN_CANCEL,
    retries=1,
)
async def block_descendants_on_failed_fn(ctx: inngest.Context) -> int:
    return await run_block_descendants_on_failed_job(
        ctx, TaskFailedEvent.model_validate(ctx.event.data)
    )


@inngest_client.create_function(
    fn_id="cancel-orphans-on-cancelled",
    trigger=inngest.TriggerEvent(event="task/cancelled"),
    cancel=RUN_CANCEL,
    retries=1,
)
async def cancel_orphans_on_cancelled_fn(ctx: inngest.Context) -> int:
    return await run_cancel_orphans_on_cancelled_job(
        ctx,
        TaskCancelledEvent.model_validate(ctx.event.data),
    )


__all__ = ["block_descendants_on_failed_fn", "cancel_orphans_on_cancelled_fn"]
