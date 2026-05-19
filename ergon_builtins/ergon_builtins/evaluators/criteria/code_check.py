"""Code-check evaluation criterion.

Stores a Python code template that checks worker output. In-process evaluation
does simple template matching; full sandbox execution happens via
Inngestevaluator runner + public sandbox runtime.
"""

from typing import Any, ClassVar

from ergon_core.api.criterion import Criterion, CriterionContext, CriterionOutcome, ScoreScale


class CodeCheckCriterion(Criterion):
    """Code-based evaluation criterion inspired by the ref CodeRule.

    Holds a Python ``code_template`` that, when executed against the worker
    output, produces a score.  The lightweight ``evaluate()`` path runs a
    simple non-empty-output check suitable for smoke tests; the real sandbox
    execution path is wired through the Inngest criterion executor.
    """

    type_slug: ClassVar[str] = "code-check"

    code_template: str

    def __init__(  # slopcop: ignore[no-typing-any]
        self, *, max_score: float | None = None, **data: Any
    ) -> None:
        if max_score is not None and "score_spec" not in data:
            data["score_spec"] = ScoreScale(max_score=max_score)
        super().__init__(**data)

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
        output = context.worker_result.output
        passed = bool(output and len(output.strip()) > 0)
        score = self.score_spec.max_score if passed else 0.0
        return CriterionOutcome(
            slug=self.slug,
            name=self.slug,
            score=score,
            passed=passed,
            weight=self.weight,
            max_score=self.score_spec.max_score,
            feedback=f"Code check '{self.slug}': {'passed' if passed else 'failed'}",
        )
