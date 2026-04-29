"""Inngest adapters for task propagation."""

import inngest

from ergon_core.core.application.jobs.propagate_execution import (
    run_propagate_task_failure_job,
    run_propagate_task_job,
)
from ergon_core.core.infrastructure.inngest.client import RUN_CANCEL, inngest_client
from ergon_core.core.infrastructure.inngest.contracts import TaskPropagateResult
from ergon_core.core.application.events.task_events import TaskCompletedEvent, TaskFailedEvent


@inngest_client.create_function(
    fn_id="task-propagate",
    trigger=inngest.TriggerEvent(event="task/completed"),
    cancel=RUN_CANCEL,
    retries=1,
    output_type=TaskPropagateResult,
)
async def propagate_task_fn(ctx: inngest.Context) -> TaskPropagateResult:
    return await run_propagate_task_job(TaskCompletedEvent.model_validate(ctx.event.data))


@inngest_client.create_function(
    fn_id="task-failure-propagate",
    trigger=inngest.TriggerEvent(event="task/failed"),
    cancel=RUN_CANCEL,
    retries=1,
    output_type=TaskPropagateResult,
)
async def propagate_task_failure_fn(ctx: inngest.Context) -> TaskPropagateResult:
    return await run_propagate_task_failure_job(TaskFailedEvent.model_validate(ctx.event.data))


__all__ = ["propagate_task_failure_fn", "propagate_task_fn"]
