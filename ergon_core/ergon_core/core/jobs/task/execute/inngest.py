"""Inngest adapter for task execution orchestration."""

import inngest

from .job import run_execute_task_job
from ergon_core.core.infrastructure.inngest.client import RUN_CANCEL, TASK_CANCEL, inngest_client
from .contract import TaskExecuteResult, TaskReadyEvent
from ergon_core.core.jobs.task.evaluate.inngest import evaluate_task_run
from ergon_core.core.jobs.resources.persist_outputs.inngest import persist_outputs_fn
from ergon_core.core.jobs.sandbox.setup.inngest import sandbox_setup_fn
from ergon_core.core.jobs.task.worker_execute.inngest import worker_execute_fn


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
        sandbox_setup_function=sandbox_setup_fn,
        worker_execute_function=worker_execute_fn,
        persist_outputs_function=persist_outputs_fn,
        evaluate_task_run_function=evaluate_task_run,
    )


__all__ = ["execute_task_fn"]
