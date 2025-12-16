"""Flatten StagedRubric into list of criteria for parallel evaluation."""

from h_arcane.evaluation.rubric import EvaluationStage, StagedRubric
from h_arcane.evaluation.rules import CodeRule, LLMJudgeRule


def flatten_rubric(
    rubric: StagedRubric,
) -> list[tuple[EvaluationStage, CodeRule | LLMJudgeRule, int, int]]:
    """
    Flatten StagedRubric into list of criteria for parallel evaluation.

    Args:
        rubric: The StagedRubric to flatten

    Returns:
        List of (stage, rule, stage_idx, rule_idx) tuples, one per rule in rubric

    Example:
        ```python
        criteria = flatten_rubric(rubric)
        for stage, rule, stage_idx, rule_idx in criteria:
            # Evaluate each criterion
            result = await evaluate_criterion(...)
        ```
    """
    criteria = []

    for stage_idx, stage in enumerate(rubric.stages):
        for rule_idx, rule in enumerate(stage.rules):
            criteria.append((stage, rule, stage_idx, rule_idx))

    return criteria
