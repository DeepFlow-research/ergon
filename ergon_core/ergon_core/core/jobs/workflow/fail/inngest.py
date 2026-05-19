"""Inngest adapter for workflow failure handling."""

import inngest

from .job import run_fail_workflow_job
from ergon_core.core.infrastructure.inngest.client import RUN_CANCEL, inngest_client
from .contract import WorkflowFailedEvent, WorkflowFailedResult


@inngest_client.create_function(
    fn_id="workflow-failed",
    trigger=inngest.TriggerEvent(event="workflow/failed"),
    cancel=RUN_CANCEL,
    retries=1,
    output_type=WorkflowFailedResult,
)
async def fail_workflow_fn(ctx: inngest.Context) -> WorkflowFailedResult:
    return await run_fail_workflow_job(WorkflowFailedEvent.model_validate(ctx.event.data))


__all__ = ["fail_workflow_fn"]
