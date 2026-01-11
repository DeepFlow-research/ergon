"""Evaluation domain - rules, runners, and evaluation workflow.

This domain handles task evaluation:
- Rule types (CodeRule, LLMJudgeRule)
- EvaluationRunner for executing rules
- Inngest functions for orchestrating evaluation

Structure:
- inngest_functions.py: Inngest function definitions (run_evaluate, evaluate_task_run, evaluate_criterion_fn)
- events.py: Event schemas (TaskEvaluationEvent, CriterionEvaluationEvent, RunEvaluateResult)
- base.py: Base evaluation types
- runner.py: EvaluationRunner
- schemas.py: Core evaluation data types
- rules/: Rule implementations (CodeRule, LLMJudgeRule)
"""

from h_arcane.core.evaluation.base import BaseRubric
from h_arcane.core.evaluation.events import (
    CriterionEvaluationEvent,
    RunEvaluateResult,
    TaskEvaluationEvent,
)
from h_arcane.core.evaluation.inngest_functions import (
    evaluate_criterion_fn,
    evaluate_task_run,
    run_evaluate,
)
from h_arcane.core.evaluation.runner import EvaluationRunner
from h_arcane.core.evaluation.schemas import EvaluationData, TaskEvaluationContext

__all__ = [
    # Base types
    "BaseRubric",
    "EvaluationRunner",
    "EvaluationData",
    "TaskEvaluationContext",
    # Inngest functions
    "run_evaluate",
    "evaluate_task_run",
    "evaluate_criterion_fn",
    # Event schemas
    "TaskEvaluationEvent",
    "CriterionEvaluationEvent",
    "RunEvaluateResult",
]
