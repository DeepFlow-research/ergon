"""Inngest adapter for sandbox output persistence."""

import inngest

from ergon_core.core.application.jobs.persist_outputs import run_persist_outputs_job
from ergon_core.core.infrastructure.inngest.client import inngest_client
from ergon_core.core.infrastructure.inngest.contracts import (
    PersistOutputsRequest,
    PersistOutputsResult,
)


@inngest_client.create_function(
    fn_id="persist-outputs",
    trigger=inngest.TriggerEvent(event="task/persist-outputs"),
    retries=1,
    output_type=PersistOutputsResult,
)
async def persist_outputs_fn(ctx: inngest.Context) -> PersistOutputsResult:
    return await run_persist_outputs_job(PersistOutputsRequest.model_validate(ctx.event.data))


__all__ = ["persist_outputs_fn"]
