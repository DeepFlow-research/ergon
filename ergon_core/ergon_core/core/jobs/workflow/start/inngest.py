"""Inngest adapter for workflow initialization."""

import inngest

from .job import run_start_workflow_job
from ergon_core.core.infrastructure.inngest.client import RUN_CANCEL, inngest_client
from .contract import SampleStartedEvent, WorkflowStartResult


@inngest_client.create_function(
    fn_id="workflow-start",
    trigger=inngest.TriggerEvent(event="sample/started"),
    cancel=RUN_CANCEL,
    retries=1,
    output_type=WorkflowStartResult,
)
async def start_workflow_fn(ctx: inngest.Context) -> WorkflowStartResult:
    return await run_start_workflow_job(SampleStartedEvent.model_validate(ctx.event.data))


__all__ = ["start_workflow_fn"]
