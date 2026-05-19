"""Inngest adapters for sandbox cleanup on terminal task events.

See ``ergon_core/core/application/jobs/sandbox_cleanup.py`` for the
full rationale. Short version: inline ``try/finally`` cleanup in the
orchestrator terminates sandboxes before workers/evaluators run because
Inngest's ``step.invoke`` raises ``ResponseInterrupt`` to suspend. This
file owns sandbox termination via sibling Inngest functions triggered by
terminal task events.
"""

import inngest

from ergon_core.core.application.events.task_events import (
    TaskCompletedEvent,
    TaskFailedEvent,
)
from ergon_core.core.application.jobs.sandbox_cleanup import (
    run_sandbox_cleanup_on_completed,
    run_sandbox_cleanup_on_failed,
)
from ergon_core.core.infrastructure.inngest.client import RUN_CANCEL, inngest_client


@inngest_client.create_function(
    fn_id="sandbox-cleanup-on-completed",
    trigger=inngest.TriggerEvent(event="task/completed"),
    cancel=RUN_CANCEL,
    retries=1,
)
async def sandbox_cleanup_on_completed_fn(ctx: inngest.Context) -> str:
    return await run_sandbox_cleanup_on_completed(
        ctx, TaskCompletedEvent.model_validate(ctx.event.data)
    )


@inngest_client.create_function(
    fn_id="sandbox-cleanup-on-failed",
    trigger=inngest.TriggerEvent(event="task/failed"),
    cancel=RUN_CANCEL,
    retries=1,
)
async def sandbox_cleanup_on_failed_fn(ctx: inngest.Context) -> str:
    return await run_sandbox_cleanup_on_failed(ctx, TaskFailedEvent.model_validate(ctx.event.data))


__all__ = [
    "sandbox_cleanup_on_completed_fn",
    "sandbox_cleanup_on_failed_fn",
]
