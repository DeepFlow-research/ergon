"""
Inngest function for task-level evaluation triggering.

This function runs evaluators bound to tasks when they complete.
"""

from __future__ import annotations

from functools import partial
from uuid import UUID

import inngest

from h_arcane.benchmarks.types import AnyRubric
from h_arcane.core._internal.db.models import TaskEvaluationResult
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.evaluation.events import TaskEvaluationEvent
from h_arcane.core._internal.evaluation.inngest_functions.task_run import evaluate_task_run
from h_arcane.core._internal.evaluation.results import EvaluatorsResult
from h_arcane.core._internal.evaluation.serialization import deserialize_rubric
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.task.events import TaskCompletedEvent
from h_arcane.core._internal.task.schema import parse_task_tree


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
    run_id = UUID(payload.run_id)
    task_id = UUID(payload.task_id)

    # Inline: Query evaluators (pure read)
    evaluators = queries.task_evaluators.get_by_task(run_id, task_id)

    if not evaluators:
        return EvaluatorsResult(
            task_id=task_id,
            evaluators_found=0,
            evaluators_run=0,
            scores=[],
        )

    # Inline: Load task execution data (pure reads)
    executions = queries.task_executions.get_by_task(run_id, task_id)
    if not executions:
        raise ValueError(f"No execution found for task {task_id}")

    latest_execution = max(executions, key=lambda e: e.attempt_number)
    outputs = queries.resources.get_outputs_for_execution(latest_execution.id)

    run = queries.runs.get(run_id)
    if not run:
        raise ValueError(f"Run {run_id} not found")

    experiment = queries.experiments.get(run.experiment_id)
    if not experiment:
        raise ValueError(f"Experiment {run.experiment_id} not found")

    tree = parse_task_tree(experiment.task_tree)
    task_node = tree.find_by_id(str(task_id)) if tree else None
    task_input = task_node.description if task_node else ""
    agent_reasoning = latest_execution.output_text or ""
    agent_outputs = list(outputs)

    # Pre-process evaluators: separate valid from invalid
    valid_evaluators: list[tuple[UUID, AnyRubric]] = []
    failed_evaluator_ids: list[UUID] = []

    for evaluator in evaluators:
        try:
            rubric = deserialize_rubric(evaluator.evaluator_type, evaluator.evaluator_config)
            valid_evaluators.append((evaluator.id, rubric))
        except ValueError:
            failed_evaluator_ids.append(evaluator.id)

    # Mark failed evaluators in parallel
    if failed_evaluator_ids:

        def make_mark_failed_step(eid: UUID):
            async def mark_failed() -> None:
                queries.task_evaluators.mark_failed(eid)

            return partial(ctx.step.run, f"mark-failed-{eid}", mark_failed)

        await ctx.group.parallel(tuple(make_mark_failed_step(eid) for eid in failed_evaluator_ids))

    # Run valid evaluators in parallel
    scores: list[float] = []
    if valid_evaluators:
        # First, mark all evaluators as running
        for eid, _ in valid_evaluators:
            queries.task_evaluators.mark_running(eid)

        # Create invokers for parallel execution
        # Note: ctx.step.invoke is already a step, so we don't wrap it in ctx.step.run
        def make_invoker(eid: UUID, r: AnyRubric):
            return lambda: ctx.step.invoke(
                step_id=f"evaluate-{eid}",
                function=evaluate_task_run,
                data=TaskEvaluationEvent(
                    run_id=str(run_id),
                    task_input=task_input,
                    agent_reasoning=agent_reasoning,
                    agent_outputs=agent_outputs,
                    rubric=r,
                ).model_dump(mode="json"),
            )

        # Execute all evaluations in parallel
        results: tuple[TaskEvaluationResult, ...] = await ctx.group.parallel(
            tuple(make_invoker(eid, rubric) for eid, rubric in valid_evaluators)
        )

        # Mark evaluators as completed with scores
        for (eid, _), result in zip(valid_evaluators, results):
            if result is not None:
                score = result.normalized_score
                queries.task_evaluators.mark_completed(eid, score)
                scores.append(score)

    return EvaluatorsResult(
        task_id=task_id,
        evaluators_found=len(evaluators),
        evaluators_run=len(scores),
        scores=scores,
    )
