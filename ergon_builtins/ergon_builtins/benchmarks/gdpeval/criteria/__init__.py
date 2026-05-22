"""GDP-specific criterion package."""

from ergon_builtins.benchmarks.gdpeval.criteria.code_check import CodeCheckCriterion
from ergon_builtins.benchmarks.gdpeval.criteria.factories import (
    content_quality_judge,
    make_code_check,
    make_llm_judge,
    output_file_exists,
)
from ergon_builtins.benchmarks.gdpeval.criteria.llm_judge import LLMJudgeCriterion

GDPEvalCriterion = CodeCheckCriterion | LLMJudgeCriterion

__all__ = [
    "CodeCheckCriterion",
    "GDPEvalCriterion",
    "LLMJudgeCriterion",
    "content_quality_judge",
    "make_code_check",
    "make_llm_judge",
    "output_file_exists",
]
