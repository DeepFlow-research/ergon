"""Evaluation system for H-ARCANE experiments.

Main exports:
- Rules: CodeRule, LLMJudgeRule, BaseRule, AnyRule
- Rubric: StagedRubric, EvaluationStage, GDPEvalStagedRubric
- Context: EvaluationData (pure data), EvaluationRunner (infrastructure)
- Schemas: SandboxResult, LLMJudgeResponse

Note: Inngest functions (evaluate_criterion_fn, evaluate_task_run) should be
imported directly from h_arcane.inngest.functions to avoid circular imports.
"""

from h_arcane.db.models import CriterionResult, Evaluation
from h_arcane.evaluation.context import EvaluationData, EvaluationRunner
from h_arcane.evaluation.rubric_flattener import flatten_rubric
from h_arcane.evaluation.rules import (
    AnyRule,
    BaseRule,
    CodeRule,
    LLMJudgeRule,
    ProofVerificationRule,
)
from h_arcane.evaluation.schemas import (
    EvaluationStage,
    GDPEvalStagedRubric,
    LLMJudgeResponse,
    SandboxResult,
    StagedRubric,
)

__all__ = [
    # Rules
    "BaseRule",
    "CodeRule",
    "LLMJudgeRule",
    "ProofVerificationRule",
    "AnyRule",
    # Rubric
    "StagedRubric",
    "EvaluationStage",
    "GDPEvalStagedRubric",
    # Context (split: data + infrastructure)
    "EvaluationData",
    "EvaluationRunner",
    # Utilities
    "flatten_rubric",
    # Database models
    "CriterionResult",
    "Evaluation",
    # Schemas
    "SandboxResult",
    "LLMJudgeResponse",
]
