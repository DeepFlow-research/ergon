"""Built-in evaluator criteria.

Stub criteria (``StubCriterion``, ``StubReportExistsCriterion``,
``VariedStubCriterion``, ``SmokeCriterionBase``) were retired alongside
the canonical-smoke refactor — test-only smoke criteria now live under
``tests/e2e/_fixtures/criteria/``.
"""

from ergon_builtins.evaluators.criteria.code_check import CodeCheckCriterion
from ergon_builtins.evaluators.criteria.llm_judge import LLMJudgeCriterion

__all__ = [
    "CodeCheckCriterion",
    "LLMJudgeCriterion",
]
