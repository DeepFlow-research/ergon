"""Inngest adapter for run cleanup."""

import inngest

from .job import run_sample_cleanup_job
from ergon_core.core.infrastructure.inngest.client import inngest_client
from .contract import SampleCleanupEvent, SampleCleanupResult


@inngest_client.create_function(
    fn_id="run-cleanup",
    trigger=inngest.TriggerEvent(event="sample/cleanup"),
    retries=0,
    output_type=SampleCleanupResult,
)
async def sample_cleanup_fn(ctx: inngest.Context) -> SampleCleanupResult:
    return await run_sample_cleanup_job(ctx, SampleCleanupEvent.model_validate(ctx.event.data))


__all__ = ["sample_cleanup_fn"]
