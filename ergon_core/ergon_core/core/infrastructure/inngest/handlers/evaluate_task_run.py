"""Inngest adapter for task evaluation."""

import inngest

from ergon_core.core.application.jobs.evaluate_task_run import run_evaluate_task_run_job
from ergon_core.core.infrastructure.inngest.client import RUN_CANCEL, inngest_client
from ergon_core.core.infrastructure.inngest.contracts import EvaluateTaskRunRequest, EvaluateTaskRunResult


@inngest_client.create_function(
    fn_id="evaluate-task-run",
    trigger=inngest.TriggerEvent(event="task/evaluate"),
    cancel=RUN_CANCEL,
    retries=1,
    output_type=EvaluateTaskRunResult,
)
async def evaluate_task_run(ctx: inngest.Context) -> EvaluateTaskRunResult:
    return await run_evaluate_task_run_job(ctx, EvaluateTaskRunRequest.model_validate(ctx.event.data))


__all__ = ["evaluate_task_run"]
