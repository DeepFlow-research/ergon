"""Check and dispatch evaluators for a completed task.

Triggered by task/completed in parallel with task_propagate.
Reads evaluator bindings from definition tables, then invokes
evaluate_task_run per evaluator. Terminates the sandbox after
all evaluations complete.
"""

import logging

import inngest
from ergon_core.core.providers.sandbox.lifecycle import terminate_sandbox_by_id
from ergon_core.core.runtime.events.task_events import (
    TaskCompletedEvent,
)
from ergon_core.core.runtime.inngest.evaluate_task_run import evaluate_task_run
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.runtime.services.child_function_payloads import (
    EvaluateTaskRunRequest,
)
from ergon_core.core.runtime.services.evaluation_dto import (
    DispatchEvaluatorsCommand,
)
from ergon_core.core.runtime.services.evaluator_dispatch_service import (
    EvaluatorDispatchService,
)
from ergon_core.core.runtime.services.inngest_function_results import (
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
    payload = TaskCompletedEvent.model_validate(ctx.event.data)
    if payload.node_id is None:
        await _terminate_sandbox(payload.sandbox_id)
        return EvaluatorsResult(
            task_id=None,
            evaluators_found=0,
            evaluators_run=0,
        )

    dispatch_service = EvaluatorDispatchService()
    dispatch = dispatch_service.prepare_dispatch(
        DispatchEvaluatorsCommand(
            run_id=payload.run_id,
            definition_id=payload.definition_id,
            node_id=payload.node_id,
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
                node_id=payload.node_id,
                task_id=payload.task_id,
                execution_id=payload.execution_id,
                evaluator_id=evaluator_payload.evaluator_id,
                evaluator_binding_key=evaluator_payload.evaluator_binding_key,
                evaluator_type=evaluator_payload.evaluator_type,
                agent_reasoning=evaluator_payload.agent_reasoning,
                sandbox_id=payload.sandbox_id,
            ).model_dump(),
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
    """Terminate the task's sandbox through the provider lifecycle boundary."""
    result = await terminate_sandbox_by_id(sandbox_id)
    logger.info(
        "Evaluator sandbox cleanup sandbox_id=%s terminated=%s reason=%s",
        result.sandbox_id,
        result.terminated,
        result.reason,
    )
