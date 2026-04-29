"""Inngest adapter for evaluator dispatch."""

import inngest

from ergon_core.core.application.jobs.check_evaluators import run_check_evaluators_job
from ergon_core.core.infrastructure.inngest.client import inngest_client
from ergon_core.core.infrastructure.inngest.contracts import EvaluatorsResult
from ergon_core.core.infrastructure.inngest.handlers.evaluate_task_run import evaluate_task_run
from ergon_core.core.application.events.task_events import TaskCompletedEvent


@inngest_client.create_function(
    fn_id="task-check-evaluators",
    trigger=inngest.TriggerEvent(event=TaskCompletedEvent.name),
    retries=1,
    output_type=EvaluatorsResult,
)
async def check_and_run_evaluators(ctx: inngest.Context) -> EvaluatorsResult:
    return await run_check_evaluators_job(
        ctx,
        TaskCompletedEvent.model_validate(ctx.event.data),
        evaluate_task_run_function=evaluate_task_run,
    )


__all__ = ["check_and_run_evaluators"]
