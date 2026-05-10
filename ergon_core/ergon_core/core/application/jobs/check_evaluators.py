"""Check and dispatch evaluators for a completed task.

Triggered by task/completed in parallel with task_propagate.
Reads task-bound evaluators from the run graph, then invokes
evaluate_task_run per evaluator. Terminates the sandbox after
all evaluations complete.
"""

import logging
from typing import Any

from ergon_core.core.application.evaluation.models import (
    DispatchEvaluatorsCommand,
)
from ergon_core.core.application.evaluation.service import (
    EvaluationService,
)
from ergon_core.core.application.jobs.models import EvaluateTaskRunRequest
from ergon_core.core.application.jobs.models import EvaluateTaskRunResult, EvaluatorsResult
from ergon_core.core.application.events.task_events import (
    TaskCompletedEvent,
)
from ergon_core.core.infrastructure.sandbox.lifecycle import SandboxLifecycleHub
from ergon_core.core.infrastructure.sandbox.lifecycle import terminate_sandbox_by_id

logger = logging.getLogger(__name__)


async def run_check_evaluators_job(
    ctx: Any,
    payload: TaskCompletedEvent,
    *,
    evaluate_task_run_function: Any,
) -> EvaluatorsResult:
    dispatch_service = EvaluationService()
    dispatch = dispatch_service.prepare_dispatch(
        DispatchEvaluatorsCommand(
            run_id=payload.run_id,
            definition_id=payload.definition_id,
            task_id=payload.task_id,
            execution_id=payload.execution_id,
        )
    )

    if not dispatch.valid_evaluators:
        await _terminate_sandbox(payload.sandbox_id, run_id=payload.run_id, task_id=payload.task_id)
        return EvaluatorsResult(
            task_id=payload.task_id,
            evaluators_found=dispatch.evaluators_found,
            evaluators_run=0,
        )

    scores: list[float | None] = []
    for evaluator_payload in dispatch.valid_evaluators:
        result: EvaluateTaskRunResult = await ctx.step.invoke(
            f"evaluate-{evaluator_payload.evaluator_index}",
            function=evaluate_task_run_function,
            data=EvaluateTaskRunRequest(
                run_id=payload.run_id,
                definition_id=payload.definition_id,
                task_id=payload.task_id,
                execution_id=payload.execution_id,
                evaluator_index=evaluator_payload.evaluator_index,
                evaluator_name=evaluator_payload.evaluator_name,
                agent_reasoning=evaluator_payload.agent_reasoning,
                sandbox_id=payload.sandbox_id,
            ).model_dump(),
        )
        scores.append(result.score)

    await _terminate_sandbox(payload.sandbox_id, run_id=payload.run_id, task_id=payload.task_id)

    return EvaluatorsResult(
        task_id=payload.task_id,
        evaluators_found=dispatch.evaluators_found,
        evaluators_run=len(dispatch.valid_evaluators),
        scores=scores,
    )


async def _terminate_sandbox(sandbox_id: str, *, run_id, task_id) -> None:
    """Terminate the task's sandbox through the provider lifecycle boundary."""
    result = await terminate_sandbox_by_id(sandbox_id)
    SandboxLifecycleHub().discard(run_id=run_id, task_id=task_id)
    logger.info(
        "Evaluator sandbox cleanup sandbox_id=%s terminated=%s reason=%s",
        result.sandbox_id,
        result.terminated,
        result.reason,
    )
