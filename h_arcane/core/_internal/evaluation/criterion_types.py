"""Discriminated union types for evaluation criteria."""

from typing import Annotated, Union

from pydantic import Field

from h_arcane.core._internal.evaluation.rules.code_rule import CodeRule
from h_arcane.core._internal.evaluation.rules.llm_judge import LLMJudgeRule
from h_arcane.benchmarks.minif2f.rules.proof_verification import ProofVerificationRule


AnyCriterion = Annotated[
    Union[CodeRule, LLMJudgeRule, ProofVerificationRule],
    Field(discriminator="type"),
]
