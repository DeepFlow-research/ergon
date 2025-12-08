"""Task run evaluator that orchestrates criterion evaluation."""

from uuid import UUID

import inngest

from h_arcane.db.models import CriterionResult, Evaluation, Resource
from h_arcane.evaluation.criteria_evaluator import evaluate_criterion
from h_arcane.evaluation.models import TaskEvaluationResult
from h_arcane.evaluation.rubric_flattener import flatten_rubric
from h_arcane.inngest.client import inngest_client
from h_arcane.schemas.staged_rubric_schema import StagedRubric


@inngest_client.create_function(  # type: ignore[misc]
    fn_id="evaluate-task-run",
    trigger=inngest.TriggerEvent(event="task/evaluate"),
    retries=2,
    concurrency=[inngest.Concurrency(limit=10, scope="fn")],
    output_type=TaskEvaluationResult,
)
async def evaluate_task_run(
    ctx: inngest.Context,
) -> TaskEvaluationResult:
    """
    Evaluate a task run against ground truth rubric.

    This is an Inngest function that evaluates all criteria in parallel.
    """
    # Extract event data (import here to avoid circular dependency)
    from h_arcane.inngest.functions import TaskEvaluationEvent

    event_data = TaskEvaluationEvent.model_validate(ctx.event.data)
    run_id = UUID(event_data.run_id)
    task_input = event_data.task_input
    agent_reasoning = event_data.agent_reasoning

    # Deserialize resources and rubric
    agent_outputs = [Resource(**r_dict) for r_dict in event_data.agent_outputs]
    rubric = StagedRubric(**event_data.rubric)

    # Flatten rubric into criteria list (as a step)
    async def flatten_rubric_step():
        criteria_tuples = flatten_rubric(rubric)
        # Convert to JSON-serializable format
        # Store stage and rule as dicts, keep indices as ints
        return [
            {
                "stage": stage.model_dump(mode="json"),
                "rule": rule.model_dump(mode="json"),
                "stage_idx": stage_idx,
                "rule_idx": rule_idx,
            }
            for stage, rule, stage_idx, rule_idx in criteria_tuples
        ]

    criteria_dicts = await ctx.step.run("flatten-rubric", flatten_rubric_step)

    # Reconstruct Pydantic objects from serialized data
    from h_arcane.schemas.staged_rubric_schema import EvaluationStage, CodeRule, LLMJudgeRule

    criteria = []
    for crit_dict in criteria_dicts:
        stage = EvaluationStage(**crit_dict["stage"])
        rule_dict = crit_dict["rule"]
        # Determine rule type based on the "type" field
        if rule_dict.get("type") == "code":
            rule = CodeRule(**rule_dict)
        else:
            rule = LLMJudgeRule(**rule_dict)
        criteria.append((stage, rule, crit_dict["stage_idx"], crit_dict["rule_idx"]))

    # Evaluate all criteria in parallel
    # Create step functions for all criteria - use helper to capture loop variables
    def make_parallel_step(s, r, si, ri, c=ctx):
        """Create a step runner function with captured variables.

        Args:
            s: Stage object
            r: Rule object
            si: Stage index
            ri: Rule index
            c: Inngest context (captured as default arg)
        """

        async def evaluate_criterion_step():
            return await evaluate_criterion(
                run_id=run_id,
                agent_reasoning=agent_reasoning,
                agent_outputs=agent_outputs,
                stage=s,
                rule=r,
                stage_idx=si,
                rule_idx=ri,
                task_input=task_input,
                sandbox_manager=None,  # Create temporary sandbox for code rules if needed
            )

        # Return lambda that calls ctx.step.run with the step function
        # Capture context and step_id in lambda defaults
        step_id = f"evaluate-criterion-{si}-{ri}"
        step_fn = evaluate_criterion_step
        return lambda ctx_ref=c, sid=step_id, fn=step_fn: ctx_ref.step.run(
            sid,
            fn,
            output_type=CriterionResult,
        )

    # Create parallel step runners - build list with proper closures
    parallel_steps_list = [
        make_parallel_step(stage, rule, stage_idx, rule_idx)
        for stage, rule, stage_idx, rule_idx in criteria
    ]

    # Run all criterion evaluations in parallel
    criterion_results_tuple = await ctx.group.parallel(tuple(parallel_steps_list))
    # Convert tuple to list for consistency
    criterion_results = list(criterion_results_tuple)

    # Rebuild into stage structure
    stage_results = _rebuild_stage_results(criterion_results, rubric)

    # Calculate aggregate scores
    aggregate = _calculate_aggregate_scores(run_id, stage_results, rubric)

    # Convert CriterionResult objects to dicts for JSON storage
    criterion_results_dicts = [cr.model_dump() for cr in criterion_results]

    return TaskEvaluationResult(
        run_id=run_id,
        criterion_results=criterion_results_dicts,
        total_score=aggregate.total_score,
        max_score=aggregate.max_score,
        normalized_score=aggregate.normalized_score,
        stages_evaluated=aggregate.stages_evaluated,
        stages_passed=aggregate.stages_passed,
        failed_gate=aggregate.failed_gate,
    )


def _rebuild_stage_results(
    criterion_results: list[CriterionResult],
    rubric: StagedRubric,
) -> list[dict]:
    """Rebuild criterion results into stage structure."""
    stage_results = []

    for stage_idx, stage in enumerate(rubric.stages):
        stage_criteria = [cr for cr in criterion_results if cr.stage_num == stage_idx]

        stage_score = sum(cr.score for cr in stage_criteria)
        stage_score = min(stage_score, stage.max_points)

        stage_result = {
            "stage_num": stage_idx,
            "stage_name": stage.name,
            "score": stage_score,
            "max_points": stage.max_points,
            "passed": stage_score >= stage.min_score_to_pass,
            "criteria": [
                {
                    "criterion_num": cr.criterion_num,
                    "criterion_type": cr.criterion_type,
                    "score": cr.score,
                    "max_score": cr.max_score,
                    "feedback": cr.feedback,
                    "evaluated_action_ids": cr.evaluated_action_ids,
                    "evaluated_resource_ids": cr.evaluated_resource_ids,
                }
                for cr in stage_criteria
            ],
        }
        stage_results.append(stage_result)

    return stage_results


def _calculate_aggregate_scores(
    run_id: UUID, stage_results: list[dict], rubric: StagedRubric
) -> Evaluation:
    """Calculate aggregate scores from stage results."""
    total_score = 0.0
    max_score = rubric.max_total_score
    stages_evaluated = 0
    stages_passed = 0
    failed_gate = None

    for stage_result in stage_results:
        stages_evaluated += 1
        total_score += stage_result["score"]

        if stage_result["passed"]:
            stages_passed += 1
        else:
            # Check if this stage was required (gate)
            stage_idx = stage_result["stage_num"]
            stage = rubric.stages[stage_idx]
            if stage.is_required and failed_gate is None:
                failed_gate = stage.name

            # Apply failure action
            if stage.on_failure_action == "skip_remaining":
                break
            elif stage.on_failure_action == "zero_category":
                total_score -= stage_result["score"]  # Remove what we added
                total_score += stage.on_failure_score

    # Normalize score
    normalized_score = total_score / max_score if max_score > 0 else 0.0
    normalized_score = min(max(normalized_score, 0.0), 1.0)

    return Evaluation(
        run_id=run_id,
        total_score=total_score,
        max_score=max_score,
        normalized_score=normalized_score,
        stages_evaluated=stages_evaluated,
        stages_passed=stages_passed,
        failed_gate=failed_gate,
    )
