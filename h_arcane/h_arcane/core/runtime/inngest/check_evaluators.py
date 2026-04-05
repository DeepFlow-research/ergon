"""Check and dispatch evaluators for a completed task.

Triggered by task/completed in parallel with task_propagate.
Reads evaluator bindings from definition tables, then invokes
evaluate_task_run per evaluator. Terminates the sandbox after
all evaluations complete.
"""

import logging

import inngest

from h_arcane.core.providers.sandbox.manager import BaseSandboxManager
from h_arcane.core.runtime.events.task_events import (
    SANDBOX_SKIPPED,
    TaskCompletedEvent,
)
from h_arcane.core.runtime.inngest.evaluate_task_run import evaluate_task_run
from h_arcane.core.runtime.inngest_client import inngest_client
from h_arcane.core.runtime.services.child_function_payloads import (
    EvaluateTaskRunRequest,
)
from h_arcane.core.runtime.services.evaluation_dto import (
    DispatchEvaluatorsCommand,
)
from h_arcane.core.runtime.services.evaluator_dispatch_service import (
    EvaluatorDispatchService,
)
from h_arcane.core.runtime.services.inngest_function_results import (
    EvaluateTaskRunResult,
    EvaluatorsResult,
)

logger = logging.getLogger(__name__)


@inngest_client.create_function(
    fn_id="task-check-evaluators",
    trigger=inngest.TriggerEvent(event=TaskCompletedEvent.name),
    retries=1,
    output_type=EvaluatorsResult,
)
async def check_and_run_evaluators(ctx: inngest.Context) -> EvaluatorsResult:
    payload = TaskCompletedEvent(**ctx.event.data)

    dispatch_service = EvaluatorDispatchService()
    dispatch = dispatch_service.prepare_dispatch(
        DispatchEvaluatorsCommand(
            run_id=payload.run_id,
            definition_id=payload.definition_id,
            task_id=payload.task_id,
            execution_id=payload.execution_id,
        )
    )

    if not dispatch.valid_evaluators:
        await _terminate_sandbox(payload.sandbox_id)
        return EvaluatorsResult(
            task_id=payload.task_id,
            evaluators_found=dispatch.evaluators_found,
            evaluators_run=0,
        )

    scores: list[float | None] = []
    for evaluator_payload in dispatch.valid_evaluators:
        result: EvaluateTaskRunResult = await ctx.step.invoke(
            f"evaluate-{evaluator_payload.evaluator_binding_key}",
            function=evaluate_task_run,
            data=EvaluateTaskRunRequest(
                run_id=payload.run_id,
                definition_id=payload.definition_id,
                task_id=payload.task_id,
                execution_id=payload.execution_id,
                evaluator_id=evaluator_payload.evaluator_id,
                evaluator_binding_key=evaluator_payload.evaluator_binding_key,
                evaluator_type=evaluator_payload.evaluator_type,
                agent_reasoning=evaluator_payload.agent_reasoning,
            ).model_dump(mode="json"),
        )
        scores.append(result.score)

    await _terminate_sandbox(payload.sandbox_id)

    return EvaluatorsResult(
        task_id=payload.task_id,
        evaluators_found=dispatch.evaluators_found,
        evaluators_run=len(dispatch.valid_evaluators),
        scores=scores,
    )


async def _terminate_sandbox(sandbox_id: str) -> None:
    """Terminate the task's sandbox if one was created."""
    if sandbox_id == SANDBOX_SKIPPED:
        return
    try:
        await BaseSandboxManager.terminate_by_sandbox_id(sandbox_id)
        logger.info("Terminated sandbox %s after evaluation", sandbox_id)
    except Exception:
        logger.error(
            "Failed to terminate sandbox %s — potential sandbox leak",
            sandbox_id, exc_info=True,
        )
