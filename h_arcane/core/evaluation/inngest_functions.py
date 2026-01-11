"""Inngest functions for the evaluation domain.

These functions orchestrate evaluation workflows via Inngest:
- run_evaluate: Top-level run evaluation (triggered after execution)
- evaluate_task_run: Task-level evaluation (delegates to rubric)
- evaluate_criterion_fn: Single criterion evaluation (for staged rubrics)

The actual evaluation logic lives in:
- rules/ (CodeRule, LLMJudgeRule)
- runner.py (EvaluationRunner)
- Rubric classes (compute_scores method)
"""

from datetime import datetime, timezone
from typing import TypeVar, cast
from uuid import UUID

import inngest

from h_arcane.benchmarks.gdpeval.sandbox import GDPEvalSandboxManager
from h_arcane.benchmarks.types import AnyRubric
from h_arcane.core.db.models import (
    CriterionResult,
    Evaluation,
    Experiment,
    Resource,
    Run,
    RunStatus,
    TaskEvaluationResult,
)
from h_arcane.core.db.queries import queries
from h_arcane.core.evaluation.events import (
    CriterionEvaluationEvent,
    RunEvaluateResult,
    TaskEvaluationEvent,
)
from h_arcane.core.evaluation.runner import EvaluationRunner
from h_arcane.core.evaluation.schemas import EvaluationData, TaskEvaluationContext
from h_arcane.core.infrastructure.inngest_client import inngest_client

T = TypeVar("T")


def _require_not_none(value: T | None, error_msg: str) -> T:
    """Helper to raise error if value is None."""
    if value is None:
        raise ValueError(error_msg)
    return value


# -----------------------------------------------------------------------------
# run_evaluate: Top-level run evaluation
# -----------------------------------------------------------------------------


@inngest_client.create_function(
    fn_id="run-evaluate",
    trigger=inngest.TriggerEvent(event="execution/done"),
    retries=0,
    output_type=RunEvaluateResult,
    concurrency=[inngest.Concurrency(limit=25, scope="fn")],
)
async def run_evaluate(
    ctx: inngest.Context,
) -> RunEvaluateResult:
    """
    Evaluate execution against ground truth rubric.

    Delegates to evaluate_task_run which orchestrates criterion evaluation.
    """
    run_id_str = str(ctx.event.data["run_id"])
    run_id = UUID(run_id_str)

    # Mark evaluating
    async def mark_evaluating():
        existing = queries.runs.get(run_id)
        if existing:
            updated = existing.model_copy(update={"status": RunStatus.EVALUATING})
            queries.runs.update(updated)
        return None

    await ctx.step.run("mark-evaluating", mark_evaluating)

    # Load state
    async def load_run_eval():
        resp = _require_not_none(queries.runs.get(run_id), f"Run {run_id} not found")
        return resp

    run = await ctx.step.run(
        "load-run",
        load_run_eval,
        output_type=Run,
    )

    if not run.experiment_id:
        raise ValueError(f"Run {run_id} has no experiment_id")

    async def load_experiment_eval():
        resp = _require_not_none(
            queries.experiments.get(run.experiment_id), f"Experiment {run.experiment_id} not found"
        )
        return resp

    experiment = await ctx.step.run(
        "load-experiment",
        load_experiment_eval,
        output_type=Experiment,
    )

    # Load output resources
    async def load_resources():
        resources = queries.resources.get_all(run_id=run_id)
        return [r.model_dump(mode="json") for r in resources]

    all_resources_dicts = await ctx.step.run(
        "load-resources",
        load_resources,
    )
    all_resources = [Resource(**r_dict) for r_dict in all_resources_dicts]
    agent_outputs = [r for r in all_resources if str(r.id) in (run.output_resource_ids or [])]

    # Invoke evaluation function (runs criteria evaluations in parallel)
    evaluation_result: TaskEvaluationResult = await ctx.step.invoke(
        step_id="invoke-evaluate-task-run",
        function=evaluate_task_run,
        data=TaskEvaluationEvent(
            run_id=str(run_id),
            task_input=experiment.task_description,
            agent_reasoning=run.output_text or "no output text",
            agent_outputs=agent_outputs,
            rubric=cast(AnyRubric, experiment.ground_truth_rubric),
        ).model_dump(mode="json"),
    )

    # Save criterion results to DB
    for cr_dict in evaluation_result.criterion_results:
        cr_dict_clean = {k: v for k, v in cr_dict.items() if k not in ("id", "run_id")}
        cr_obj = CriterionResult(**cr_dict_clean, run_id=run_id)

        async def store_criterion(criterion_result=cr_obj):
            return queries.criterion_results.create_from_eval(
                run_id=run_id, eval_result=criterion_result
            )

        await ctx.step.run(
            f"store-criterion-{cr_obj.stage_num}-{cr_obj.criterion_num}",
            store_criterion,
            output_type=CriterionResult,
        )

    # Store aggregate evaluation
    async def store_evaluation():
        eval_instance = Evaluation(
            run_id=run_id,
            total_score=evaluation_result.total_score,
            max_score=evaluation_result.max_score,
            normalized_score=evaluation_result.normalized_score,
            stages_evaluated=evaluation_result.stages_evaluated,
            stages_passed=evaluation_result.stages_passed,
            failed_gate=evaluation_result.failed_gate,
        )
        return queries.evaluations.create_from_eval(
            run_id=run_id,
            eval_result=eval_instance,
        )

    await ctx.step.run(
        "store-evaluation",
        store_evaluation,
        output_type=Evaluation,
    )

    # Store complete task evaluation result snapshot (idempotent)
    async def store_task_evaluation_result():
        existing = queries.task_evaluation_results.get_by_run(run_id)

        if existing:
            updated = existing.model_copy(
                update={
                    "criterion_results": evaluation_result.criterion_results,
                    "total_score": evaluation_result.total_score,
                    "max_score": evaluation_result.max_score,
                    "normalized_score": evaluation_result.normalized_score,
                    "stages_evaluated": evaluation_result.stages_evaluated,
                    "stages_passed": evaluation_result.stages_passed,
                    "failed_gate": evaluation_result.failed_gate,
                }
            )
            return queries.task_evaluation_results.update(updated)
        else:
            return queries.task_evaluation_results.create(
                TaskEvaluationResult(
                    run_id=run_id,
                    criterion_results=evaluation_result.criterion_results,
                    total_score=evaluation_result.total_score,
                    max_score=evaluation_result.max_score,
                    normalized_score=evaluation_result.normalized_score,
                    stages_evaluated=evaluation_result.stages_evaluated,
                    stages_passed=evaluation_result.stages_passed,
                    failed_gate=evaluation_result.failed_gate,
                )
            )

    await ctx.step.run(
        "store-task-evaluation-result",
        store_task_evaluation_result,
        output_type=TaskEvaluationResult,
    )

    # Mark complete
    async def complete_run():
        existing = queries.runs.get(run_id)
        if existing:
            updated = existing.model_copy(
                update={
                    "status": RunStatus.COMPLETED,
                    "completed_at": datetime.now(timezone.utc),
                    "final_score": evaluation_result.total_score,
                    "normalized_score": evaluation_result.normalized_score,
                    "questions_asked": run.questions_asked or 0,
                }
            )
            queries.runs.update(updated)
        return None

    await ctx.step.run(
        "complete-run",
        complete_run,
    )

    return RunEvaluateResult(
        run_id=str(run_id),
        normalized_score=evaluation_result.normalized_score,
        questions_asked=run.questions_asked or 0,
    )


# -----------------------------------------------------------------------------
# evaluate_task_run: Task-level evaluation (delegates to rubric)
# -----------------------------------------------------------------------------


@inngest_client.create_function(
    fn_id="evaluate-task-run",
    trigger=inngest.TriggerEvent(event="task/evaluate"),
    retries=0,
    concurrency=[inngest.Concurrency(limit=10, scope="fn")],
    output_type=TaskEvaluationResult,
)
async def evaluate_task_run(ctx: inngest.Context) -> TaskEvaluationResult:
    """
    Evaluate a task run by delegating to rubric.compute_scores().

    Pydantic handles all deserialization automatically via model_validate():
    - agent_outputs: list[Resource] auto-deserialized
    - rubric: AnyRubric auto-selects correct type via discriminator
    """
    event_data = TaskEvaluationEvent.model_validate(ctx.event.data)
    run_id = UUID(event_data.run_id)

    context = TaskEvaluationContext(
        run_id=run_id,
        task_input=event_data.task_input,
        agent_reasoning=event_data.agent_reasoning,
        agent_outputs=event_data.agent_outputs,
        rubric=event_data.rubric,
    )

    # Polymorphic dispatch - each rubric type implements its own scoring
    result = await event_data.rubric.compute_scores(context, ctx)

    return result


# -----------------------------------------------------------------------------
# evaluate_criterion_fn: Single criterion evaluation (for staged rubrics)
# -----------------------------------------------------------------------------


@inngest_client.create_function(
    fn_id="evaluate-criterion",
    trigger=inngest.TriggerEvent(event="criterion/evaluate"),
    retries=0,
    concurrency=[inngest.Concurrency(limit=20, scope="fn")],
    output_type=CriterionResult,
)
async def evaluate_criterion_fn(
    ctx: inngest.Context,
) -> CriterionResult:
    """
    Evaluate a single criterion against task outputs.

    Pydantic handles deserialization automatically via model_validate():
    - agent_outputs: list[Resource] auto-deserialized
    - rule: AnyRule auto-selects correct type via discriminator

    Note: criteria_evaluator is currently only used for GDPEval (staged rubrics
    with code/LLM rules). The sandbox manager is hardcoded for now but could
    be made generic via registry if other benchmarks need staged evaluation.
    """
    event_data = CriterionEvaluationEvent.model_validate(ctx.event.data)
    run_id = UUID(event_data.run_id)

    data = EvaluationData(
        run_id=run_id,
        task_input=event_data.task_input,
        agent_reasoning=event_data.agent_reasoning,
        agent_outputs=event_data.agent_outputs,
        stage_idx=event_data.stage_idx,
        stage_name=event_data.stage_name,
        rule_idx=event_data.rule_idx,
        max_score=event_data.max_score,
    )

    # Create sandbox manager and runner with Inngest context for step tracing
    # TODO: Make sandbox manager generic via registry if other benchmarks need staged evaluation
    sandbox_manager = GDPEvalSandboxManager()
    runner = EvaluationRunner(data, sandbox_manager, inngest_ctx=ctx)

    result = await event_data.rule.evaluate(runner)

    async def cleanup() -> dict:
        await runner.cleanup()
        return {"cleaned_up": True}

    await ctx.step.run("cleanup", cleanup)

    return result
