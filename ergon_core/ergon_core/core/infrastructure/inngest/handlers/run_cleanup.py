"""Inngest adapter for run cleanup."""

import inngest

from ergon_core.core.application.jobs.run_cleanup import run_run_cleanup_job
from ergon_core.core.infrastructure.inngest.client import inngest_client
from ergon_core.core.infrastructure.inngest.contracts import RunCleanupResult
from ergon_core.core.application.events.infrastructure_events import RunCleanupEvent


@inngest_client.create_function(
    fn_id="run-cleanup",
    trigger=inngest.TriggerEvent(event="run/cleanup"),
    retries=0,
    output_type=RunCleanupResult,
)
async def run_cleanup_fn(ctx: inngest.Context) -> RunCleanupResult:
    return await run_run_cleanup_job(ctx, RunCleanupEvent.model_validate(ctx.event.data))


__all__ = ["run_cleanup_fn"]
