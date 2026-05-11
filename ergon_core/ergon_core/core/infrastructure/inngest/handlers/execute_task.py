"""Inngest adapter for task execution orchestration."""

import inngest

from ergon_core.core.application.jobs.execute_task import run_execute_task_job
from ergon_core.core.infrastructure.inngest.client import RUN_CANCEL, TASK_CANCEL, inngest_client
from ergon_core.core.infrastructure.inngest.contracts import TaskExecuteResult
from ergon_core.core.infrastructure.inngest.handlers.worker_execute import worker_execute_fn
from ergon_core.core.application.events.task_events import TaskReadyEvent


@inngest_client.create_function(
    fn_id="task-execute",
    trigger=inngest.TriggerEvent(event="task/ready"),
    cancel=[*RUN_CANCEL, *TASK_CANCEL],
    retries=0,
    concurrency=[inngest.Concurrency(limit=15)],
    output_type=TaskExecuteResult,
)
async def execute_task_fn(ctx: inngest.Context) -> TaskExecuteResult:
    return await run_execute_task_job(
        ctx,
        TaskReadyEvent.model_validate(ctx.event.data),
        worker_execute_function=worker_execute_fn,
    )


__all__ = ["execute_task_fn"]
