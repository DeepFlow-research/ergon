"""Inngest adapter for task execution orchestration."""

import inngest

from ergon_core.core.application.jobs.execute_task import run_execute_task_job
from ergon_core.core.infrastructure.inngest.client import RUN_CANCEL, TASK_CANCEL, inngest_client
from ergon_core.core.infrastructure.inngest.contracts import TaskExecuteResult
from ergon_core.core.infrastructure.inngest.handlers.evaluate_task_run import evaluate_task_run
from ergon_core.core.infrastructure.inngest.handlers.persist_outputs import persist_outputs_fn
from ergon_core.core.infrastructure.inngest.handlers.sandbox_setup import sandbox_setup_fn
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
        sandbox_setup_function=sandbox_setup_fn,
        worker_execute_function=worker_execute_fn,
        persist_outputs_function=persist_outputs_fn,
        evaluate_task_run_function=evaluate_task_run,
    )


__all__ = ["execute_task_fn"]
