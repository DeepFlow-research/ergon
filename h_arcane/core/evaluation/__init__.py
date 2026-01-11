"""Evaluation domain - rules, runners, and evaluation workflow.

This domain handles task evaluation:
- Rule types (CodeRule, LLMJudgeRule)
- EvaluationRunner for executing rules
- Inngest functions for orchestrating evaluation

Structure:
- inngest_functions.py: Inngest function definitions
- events.py: Event schemas
- base.py: Base evaluation types
- runner.py: EvaluationRunner
- schemas.py: Core evaluation data types
- rules/: Rule implementations (CodeRule, LLMJudgeRule)

Import from submodules directly to avoid circular imports:
    from h_arcane.core.evaluation.rules import CodeRule, LLMJudgeRule
    from h_arcane.core.evaluation.runner import EvaluationRunner
    from h_arcane.core.evaluation.inngest_functions import run_evaluate
    from h_arcane.core.evaluation.events import TaskEvaluationEvent
"""

# Intentionally empty to avoid circular imports.
# Import from submodules directly.
