"""Inngest adapter for worker execution."""

import inngest

from .job import run_worker_execute_job
from ergon_core.core.infrastructure.inngest.client import RUN_CANCEL, TASK_CANCEL, inngest_client
from .contract import WorkerExecuteRequest, WorkerExecuteResult


@inngest_client.create_function(
    fn_id="worker-execute",
    trigger=inngest.TriggerEvent(event="task/worker-execute"),
    cancel=[*RUN_CANCEL, *TASK_CANCEL],
    retries=0,
    output_type=WorkerExecuteResult,
)
async def worker_execute_fn(ctx: inngest.Context) -> WorkerExecuteResult:
    return await run_worker_execute_job(
        WorkerExecuteRequest.model_validate(ctx.event.data), ctx=ctx
    )


__all__ = ["worker_execute_fn"]
