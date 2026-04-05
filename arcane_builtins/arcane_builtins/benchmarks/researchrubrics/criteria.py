"""Research-specific LLM-judge criterion instances.

Each ``RubricCriterion`` from the dataset is converted into a lightweight
``LLMJudgeCriterion`` whose prompt encodes the evaluation axis and weight.
"""

from __future__ import annotations

from arcane_builtins.benchmarks.researchrubrics.task_schemas import RubricCriterion
from arcane_builtins.evaluators.criteria.llm_judge import LLMJudgeCriterion


def _build_judge_prompt(criterion: RubricCriterion) -> str:
    """Build a system prompt for the LLM judge evaluating a single criterion."""
    axis_context = (
        f"\n\nThis criterion belongs to the '{criterion.axis}' axis." if criterion.axis else ""
    )
    weight_note = f"\n\nWeight: {criterion.weight}" if criterion.weight != 1.0 else ""

    return (
        "You are an expert evaluator assessing research reports against specific criteria.\n\n"
        "Your task is to evaluate whether a research report meets this criterion:\n"
        f"{criterion.criterion}{axis_context}{weight_note}\n\n"
        "You will be given:\n"
        "- The original task/request given to the researcher\n"
        "- The researcher's reasoning and thought process\n"
        "- The final research report/output\n\n"
        "Evaluate whether the output meets this criterion. Provide:\n"
        "1. Detailed reasoning explaining your decision, citing specific evidence "
        "from the task input, researcher reasoning, and outputs\n"
        "2. A binary verdict: True if the criterion is met, False otherwise\n\n"
        "This is a pass/fail decision. The criterion is either satisfied (True) "
        "or not satisfied (False).\n"
        "Be thorough but fair in your evaluation."
    )


def build_criteria_from_rubrics(
    rubric_criteria: list[RubricCriterion],
) -> list[LLMJudgeCriterion]:
    """Convert raw dataset criteria into executable ``LLMJudgeCriterion`` instances.

    Each criterion gets:
    - ``weight`` = the raw rubric weight (can be negative)
    - ``max_score`` = ``abs(weight)`` (binary pass/fail threshold)
    """
    return [
        LLMJudgeCriterion(
            name=f"criterion_{idx}",
            prompt_template=_build_judge_prompt(criterion),
            description=criterion.criterion,
            weight=criterion.weight,
            max_score=abs(criterion.weight),
        )
        for idx, criterion in enumerate(rubric_criteria)
    ]
