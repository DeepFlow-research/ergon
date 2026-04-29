"""Inngest adapter for worker execution."""

import inngest

from ergon_core.core.application.jobs.worker_execute import run_worker_execute_job
from ergon_core.core.infrastructure.inngest.client import inngest_client
from ergon_core.core.infrastructure.inngest.contracts import WorkerExecuteRequest, WorkerExecuteResult


@inngest_client.create_function(
    fn_id="worker-execute",
    trigger=inngest.TriggerEvent(event="task/worker-execute"),
    retries=0,
    output_type=WorkerExecuteResult,
)
async def worker_execute_fn(ctx: inngest.Context) -> WorkerExecuteResult:
    return await run_worker_execute_job(WorkerExecuteRequest.model_validate(ctx.event.data))


__all__ = ["worker_execute_fn"]
