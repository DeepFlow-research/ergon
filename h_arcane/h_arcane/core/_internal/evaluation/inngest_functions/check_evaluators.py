"""
Inngest function for task-level evaluation triggering.

This function runs evaluators bound to tasks when they complete.
"""

from __future__ import annotations

from functools import partial
from uuid import UUID

import inngest

from h_arcane.core._internal.db.models import TaskEvaluationResult
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.evaluation.events import TaskEvaluationEvent
from h_arcane.core._internal.evaluation.inngest_functions.task_run import evaluate_task_run
from h_arcane.core._internal.evaluation.results import EvaluatorsResult
from h_arcane.core._internal.evaluation.services import EvaluatorDispatchService
from h_arcane.core._internal.evaluation.services.dto import (
    DispatchEvaluatorsCommand,
    PreparedEvaluatorDispatch,
)
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.task.events import TaskCompletedEvent


@inngest_client.create_function(
    fn_id="task-check-evaluators",
    trigger=inngest.TriggerEvent(event=TaskCompletedEvent.name),
    retries=1,
    output_type=EvaluatorsResult,
)
async def check_and_run_evaluators(ctx: inngest.Context) -> EvaluatorsResult:
    """
    Check if completed task has evaluators and run them.

    Subscribes to task/completed event (same as task_propagate).
    Multiple Inngest functions can subscribe to the same event.

    This function:
    1. Queries TaskEvaluator records (inlined)
    2. Loads task execution data (inlined)
    3. For each evaluator, invokes evaluate_task_run
    4. Updates TaskEvaluator status and score
    """
    payload = TaskCompletedEvent.model_validate(ctx.event.data)
    run_id = payload.run_id
    task_id = payload.task_id
    prepared = await ctx.step.run(
        "prepare-evaluator-dispatch",
        lambda: EvaluatorDispatchService().prepare_dispatch(
            DispatchEvaluatorsCommand(
                run_id=run_id,
                task_id=task_id,
                execution_id=payload.execution_id,
                experiment_id=payload.experiment_id,
            )
        ),
        output_type=PreparedEvaluatorDispatch,
    )

    if prepared.evaluators_found == 0:
        return EvaluatorsResult(
            task_id=task_id,
            evaluators_found=0,
            evaluators_run=0,
            scores=[],
        )

    # Mark failed evaluators in parallel
    if prepared.invalid_evaluator_ids:

        def make_mark_failed_step(eid: UUID):
            async def mark_failed() -> None:
                queries.task_evaluators.mark_failed(eid)

            return partial(ctx.step.run, f"mark-failed-{eid}", mark_failed)

        await ctx.group.parallel(
            tuple(make_mark_failed_step(eid) for eid in prepared.invalid_evaluator_ids)
        )

    # Run valid evaluators in parallel
    scores: list[float] = []
    if prepared.valid_evaluators:
        # First, mark all evaluators as running
        for evaluator in prepared.valid_evaluators:
            queries.task_evaluators.mark_running(evaluator.evaluator_id)

        # Create invokers for parallel execution
        # Note: ctx.step.invoke is already a step, so we don't wrap it in ctx.step.run
        def make_invoker(evaluator_id: UUID, evaluator_payload: TaskEvaluationEvent):
            return lambda: ctx.step.invoke(
                step_id=f"evaluate-{evaluator_id}",
                function=evaluate_task_run,
                data=evaluator_payload.model_dump(mode="json"),
            )

        # Execute all evaluations in parallel
        results: tuple[TaskEvaluationResult, ...] = await ctx.group.parallel(
            tuple(
                make_invoker(
                    evaluator.evaluator_id,
                    TaskEvaluationEvent(
                        run_id=run_id,
                        task_id=task_id,
                        execution_id=payload.execution_id,
                        evaluator_id=evaluator.evaluator_id,
                        task_input=evaluator.task_input,
                        agent_reasoning=evaluator.agent_reasoning,
                        agent_outputs=evaluator.agent_outputs,
                        rubric=evaluator.rubric,
                    ),
                )
                for evaluator in prepared.valid_evaluators
            )
        )

        # Mark evaluators as completed with scores
        for evaluator, result in zip(prepared.valid_evaluators, results):
            if result is not None:
                score = result.normalized_score
                queries.task_evaluators.mark_completed(evaluator.evaluator_id, score)
                scores.append(score)

    return EvaluatorsResult(
        task_id=task_id,
        evaluators_found=prepared.evaluators_found,
        evaluators_run=len(scores),
        scores=scores,
    )
