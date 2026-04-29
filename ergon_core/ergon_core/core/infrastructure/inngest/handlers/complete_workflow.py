"""Inngest adapter for workflow completion finalization."""

import inngest

from ergon_core.core.application.jobs.complete_workflow import run_complete_workflow_job
from ergon_core.core.infrastructure.inngest.client import RUN_CANCEL, inngest_client
from ergon_core.core.infrastructure.inngest.contracts import WorkflowCompleteResult
from ergon_core.core.application.events.task_events import WorkflowCompletedEvent


@inngest_client.create_function(
    fn_id="workflow-complete",
    trigger=inngest.TriggerEvent(event="workflow/completed"),
    cancel=RUN_CANCEL,
    retries=1,
    output_type=WorkflowCompleteResult,
)
async def complete_workflow_fn(ctx: inngest.Context) -> WorkflowCompleteResult:
    return await run_complete_workflow_job(WorkflowCompletedEvent.model_validate(ctx.event.data))


__all__ = ["complete_workflow_fn"]
