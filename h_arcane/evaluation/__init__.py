"""Evaluation system for H-ARCANE experiments.

Main exports:
- Rules: CodeRule, LLMJudgeRule, BaseRule, AnyRule
- Rubric: StagedRubric, EvaluationStage, GDPEvalStagedRubric
- Context: EvaluationData (pure data), EvaluationRunner (infrastructure)
- Functions: evaluate_criterion_fn (Inngest), evaluate_task_run
- Schemas: SandboxResult, LLMJudgeResponse
"""

from h_arcane.db.models import CriterionResult, Evaluation
from h_arcane.evaluation.context import EvaluationData, EvaluationRunner
from h_arcane.evaluation.criteria_evaluator import evaluate_criterion_fn
from h_arcane.evaluation.rubric import (
    EvaluationStage,
    GDPEvalStagedRubric,
    StagedRubric,
)
from h_arcane.evaluation.rubric_flattener import flatten_rubric
from h_arcane.evaluation.rules import AnyRule, BaseRule, CodeRule, LLMJudgeRule
from h_arcane.evaluation.schemas import LLMJudgeResponse, SandboxResult
from h_arcane.evaluation.task_evaluator import evaluate_task_run

__all__ = [
    # Rules
    "BaseRule",
    "CodeRule",
    "LLMJudgeRule",
    "AnyRule",
    # Rubric
    "StagedRubric",
    "EvaluationStage",
    "GDPEvalStagedRubric",
    # Context (split: data + infrastructure)
    "EvaluationData",
    "EvaluationRunner",
    # Functions
    "evaluate_criterion_fn",
    "evaluate_task_run",
    "flatten_rubric",
    # Database models
    "CriterionResult",
    "Evaluation",
    # Schemas
    "SandboxResult",
    "LLMJudgeResponse",
]
