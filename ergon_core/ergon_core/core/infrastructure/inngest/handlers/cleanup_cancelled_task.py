"""Inngest adapter for cancelled task cleanup."""

import inngest

from ergon_core.core.application.jobs.cleanup_cancelled_task import run_cleanup_cancelled_task_job
from ergon_core.core.infrastructure.inngest.client import RUN_CANCEL, inngest_client
from ergon_core.core.application.events.task_events import TaskCancelledEvent
from ergon_core.core.shared.json_types import JsonObject


@inngest_client.create_function(
    fn_id="cleanup-cancelled-task",
    trigger=inngest.TriggerEvent(event="task/cancelled"),
    cancel=RUN_CANCEL,
    retries=3,
)
async def cleanup_cancelled_task_fn(ctx: inngest.Context) -> JsonObject:
    return await run_cleanup_cancelled_task_job(ctx, TaskCancelledEvent.model_validate(ctx.event.data))


__all__ = ["cleanup_cancelled_task_fn"]
