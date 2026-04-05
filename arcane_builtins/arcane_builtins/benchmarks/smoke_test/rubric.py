"""Smoke-test rubric with real CodeCheck + LLMJudge criteria."""

from __future__ import annotations

from typing import ClassVar

from h_arcane.api.evaluator import Rubric

from arcane_builtins.evaluators.criteria.code_check import CodeCheckCriterion
from arcane_builtins.evaluators.criteria.llm_judge import LLMJudgeCriterion


class SmokeTestRubric(Rubric):
    """Rubric for the smoke-test benchmark.

    Bundles a ``CodeCheckCriterion`` (output-exists) and an
    ``LLMJudgeCriterion`` (output-quality), each worth 0.5 points.
    """

    type_slug: ClassVar[str] = "smoke-test-rubric"

    def __init__(self, *, name: str = "smoke-test-rubric") -> None:
        super().__init__(
            name=name,
            criteria=[
                CodeCheckCriterion(
                    name="output-exists",
                    code_template="len(output) > 0",
                    description="Check that output is non-empty",
                    max_score=0.5,
                ),
                LLMJudgeCriterion(
                    name="output-quality",
                    prompt_template="Is this a reasonable response?",
                    description="Judge output quality",
                    max_score=0.5,
                ),
            ],
        )
