"""Task run evaluator that orchestrates criterion evaluation."""

from uuid import UUID

from h_arcane.db.models import CriterionResult, Evaluation, Resource
from h_arcane.evaluation.criteria_evaluator import evaluate_criterion
from h_arcane.evaluation.models import TaskEvaluationResult
from h_arcane.evaluation.rubric_flattener import flatten_rubric
from h_arcane.schemas.staged_rubric_schema import StagedRubric


async def evaluate_task_run(
    run_id: UUID,
    task_input: str,
    agent_reasoning: str,
    agent_outputs: list[Resource],
    rubric: StagedRubric,
    sandbox_manager=None,
) -> TaskEvaluationResult:
    """
    Evaluate a task run against ground truth rubric.

    Args:
        run_id: The run ID
        task_input: Original task description
        agent_reasoning: Worker's reasoning/output text
        agent_outputs: Output files/resources
        rubric: Ground truth StagedRubric
        sandbox_manager: Optional sandbox manager for code rule execution

    Returns:
        TaskEvaluationResult with aggregate scores and evaluation summary

    Example:
        ```python
        result = await evaluate_task_run(
            run_id=run_id,
            task_input="Create a report",
            agent_reasoning="I created a PDF...",
            agent_outputs=[resource1, resource2],
            rubric=staged_rubric,
            sandbox_manager=sandbox_manager
        )
        print(f"Score: {result.normalized_score:.2%}")
        ```
    """
    # Flatten rubric into criteria list
    criteria = flatten_rubric(rubric)

    # Evaluate all criteria (can be parallelized via Inngest step.invoke)
    criterion_results = []
    for stage, rule, stage_idx, rule_idx in criteria:
        result = await evaluate_criterion(
            run_id=run_id,
            agent_reasoning=agent_reasoning,
            agent_outputs=agent_outputs,
            stage=stage,
            rule=rule,
            stage_idx=stage_idx,
            rule_idx=rule_idx,
            task_input=task_input,
            sandbox_manager=sandbox_manager,
        )
        criterion_results.append(result)

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
