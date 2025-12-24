"""Discriminated union types for benchmarks.

This module defines type unions that allow Pydantic to automatically
select the correct concrete type during deserialization based on
discriminator fields.

Separated from registry.py to avoid circular imports with core modules.
"""

from typing import Annotated, Union

from pydantic import Field

from h_arcane.benchmarks.gdpeval.rubric import StagedRubric
from h_arcane.benchmarks.minif2f.rubric import MiniF2FRubric
from h_arcane.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from h_arcane.core.evaluation.rules import CodeRule, LLMJudgeRule
from h_arcane.benchmarks.minif2f.rules import ProofVerificationRule


# Discriminated union for rubrics - Pydantic auto-selects based on "benchmark" field
AnyRubric = Annotated[
    Union[StagedRubric, MiniF2FRubric, ResearchRubricsRubric],
    Field(discriminator="benchmark"),
]

# Discriminated union for rules - Pydantic auto-selects based on "type" field
AnyRule = Annotated[
    Union[CodeRule, LLMJudgeRule, ProofVerificationRule],
    Field(discriminator="type"),
]
