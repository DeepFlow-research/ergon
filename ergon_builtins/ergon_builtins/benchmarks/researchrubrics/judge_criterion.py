from typing import ClassVar

from ergon_core.api.criterion import Criterion
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.results import CriterionResult
from ergon_core.core.providers.generation.structured_judge import (
    JudgeMessage,
    call_structured_judge,
)
from pydantic import BaseModel

from ergon_builtins.benchmarks.researchrubrics.task_schemas import RubricCriterion


class ResearchRubricsVerdict(BaseModel):
    reasoning: str
    passed: bool


class ResearchRubricsJudgeCriterion(Criterion):
    """ResearchRubrics-specific LLM judge for one dataset rubric item."""

    type_slug: ClassVar[str] = "researchrubrics-llm-judge"

    def __init__(
        self,
        *,
        name: str,
        rubric: RubricCriterion,
        model: str = "openai:gpt-4o",
    ) -> None:
        super().__init__(name=name, weight=rubric.weight)
        self.rubric = rubric
        self.max_score = abs(rubric.weight)
        self.model = model
        self.system_prompt = _build_system_prompt(rubric)

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        verdict = await call_structured_judge(
            messages=[
                JudgeMessage(role="system", content=self.system_prompt),
                JudgeMessage(role="user", content=_build_user_prompt(context)),
            ],
            response_type=ResearchRubricsVerdict,
            model=self.model,
        )
        return CriterionResult(
            name=self.name,
            score=self.max_score if verdict.passed else 0.0,
            passed=verdict.passed,
            weight=self.weight,
            feedback=verdict.reasoning,
        )


def _build_system_prompt(criterion: RubricCriterion) -> str:
    axis_context = (
        f"\n\nThis criterion belongs to the ResearchRubrics '{criterion.axis}' axis."
        if criterion.axis
        else ""
    )
    weight_note = f"\n\nResearchRubrics weight: {criterion.weight}"
    return (
        "You are an expert ResearchRubrics evaluator assessing deep-research reports.\n\n"
        "Evaluate whether the report satisfies this exact rubric criterion:\n"
        f"{criterion.criterion}{axis_context}{weight_note}\n\n"
        "Use the original research request, the agent's reasoning when present, "
        "and the final report/output as evidence. Return a binary verdict: "
        "`passed=true` only when the criterion is clearly satisfied. Explain the "
        "decision with concrete evidence from the provided material."
    )


def _build_user_prompt(context: EvaluationContext) -> str:
    return (
        f"Original research request:\n{context.task.description}\n\n"
        f"Researcher output:\n{context.worker_result.output}"
    )
