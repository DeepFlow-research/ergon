"""ResearchRubrics-specific LLM-judge criterion instances.

Each ``RubricCriterion`` from the dataset is converted into a lightweight
``ResearchRubricsJudgeCriterion`` whose prompt encodes the evaluation axis
and weight.
"""

from ergon_builtins.benchmarks.researchrubrics.judge_criterion import (
    ResearchRubricsJudgeCriterion,
)
from ergon_builtins.benchmarks.researchrubrics.task_schemas import RubricCriterion


def build_criteria_from_rubrics(
    rubric_criteria: list[RubricCriterion],
) -> list[ResearchRubricsJudgeCriterion]:
    """Convert raw dataset criteria into executable ResearchRubrics judges.

    Each criterion gets:
    - ``weight`` = the raw rubric weight (can be negative)
    - ``max_score`` = ``abs(weight)`` (binary pass/fail threshold)
    """
    return [
        ResearchRubricsJudgeCriterion(
            name=f"criterion_{idx}",
            rubric=criterion,
        )
        for idx, criterion in enumerate(rubric_criteria)
    ]
