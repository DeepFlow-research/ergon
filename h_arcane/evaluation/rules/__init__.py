"""Rule classes for evaluation."""

from h_arcane.evaluation.rules.base import BaseRule
from h_arcane.evaluation.rules.code_rule import CodeRule
from h_arcane.evaluation.rules.llm_judge import LLMJudgeRule
from h_arcane.evaluation.rules.proof_verification import ProofVerificationRule

from typing import Annotated, Union
from pydantic import Field

# Discriminated union for type-safe rule handling
AnyRule = Annotated[
    Union[CodeRule, LLMJudgeRule, ProofVerificationRule],
    Field(discriminator="type"),
]

# Benchmark-specific type aliases
GDPEvalRule = Annotated[Union[CodeRule, LLMJudgeRule], Field(discriminator="type")]
MiniF2FRule = ProofVerificationRule

__all__ = [
    "BaseRule",
    "CodeRule",
    "LLMJudgeRule",
    "ProofVerificationRule",
    "AnyRule",
    "GDPEvalRule",
    "MiniF2FRule",
]
