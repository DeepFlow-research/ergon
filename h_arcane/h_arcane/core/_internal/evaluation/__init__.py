"""Evaluation domain - criteria, runtimes, services, and orchestration.

This domain handles task evaluation:
- Criterion types (CodeRule, LLMJudgeRule, ProofVerificationRule)
- DefaultCriterionRuntime for executing a single criterion
- RubricEvaluationService for task-level aggregation
- Inngest functions for orchestrating evaluation

Structure:
- inngest_functions.py: Inngest function definitions (evaluate_task_run, evaluate_criterion_fn)
- events.py: Event schemas
- base.py: Base evaluation types
- runtime.py: Criterion runtime interface + default implementation
- inngest_executor.py: Inngest-backed criterion executor
- services/: Task-level rubric evaluation services
- schemas.py: Core evaluation data types
- rules/: Criterion implementations

Import from submodules directly to avoid circular imports:
    from h_arcane.core._internal.evaluation.rules import CodeRule, LLMJudgeRule
    from h_arcane.core._internal.evaluation.runtime import DefaultCriterionRuntime
    from h_arcane.core._internal.evaluation.inngest_functions import evaluate_task_run
    from h_arcane.core._internal.evaluation.events import TaskEvaluationEvent
"""

# Intentionally empty to avoid circular imports.
# Import from submodules directly.
