"""Rule classes for evaluation."""

from h_arcane.evaluation.rules.base import BaseRule
from h_arcane.evaluation.rules.code_rule import CodeRule
from h_arcane.evaluation.rules.llm_judge import LLMJudgeRule

from typing import Annotated, Union
from pydantic import Field

# Discriminated union for type-safe rule handling
AnyRule = Annotated[Union[CodeRule, LLMJudgeRule], Field(discriminator="type")]

# Benchmark-specific type aliases
GDPEvalRule = AnyRule

__all__ = ["BaseRule", "CodeRule", "LLMJudgeRule", "AnyRule", "GDPEvalRule"]
