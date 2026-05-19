"""Inngest adapter for sandbox setup."""

import inngest

from .job import run_sandbox_setup_job
from ergon_core.core.infrastructure.inngest.client import inngest_client
from .contract import SandboxReadyResult, SandboxSetupRequest


@inngest_client.create_function(
    fn_id="sandbox-setup",
    trigger=inngest.TriggerEvent(event="task/sandbox-setup"),
    retries=1,
    output_type=SandboxReadyResult,
)
async def sandbox_setup_fn(ctx: inngest.Context) -> SandboxReadyResult:
    return await run_sandbox_setup_job(ctx, SandboxSetupRequest.model_validate(ctx.event.data))


__all__ = ["sandbox_setup_fn"]
