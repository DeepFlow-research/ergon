"""Inngest adapter for run cleanup."""

import inngest

from .job import run_run_cleanup_job
from ergon_core.core.infrastructure.inngest.client import inngest_client
from .contract import RunCleanupEvent, RunCleanupResult


@inngest_client.create_function(
    fn_id="run-cleanup",
    trigger=inngest.TriggerEvent(event="run/cleanup"),
    retries=0,
    output_type=RunCleanupResult,
)
async def run_cleanup_fn(ctx: inngest.Context) -> RunCleanupResult:
    return await run_run_cleanup_job(ctx, RunCleanupEvent.model_validate(ctx.event.data))


__all__ = ["run_cleanup_fn"]
