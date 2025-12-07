"""Evaluation result models.

Note: All models are now imported directly from h_arcane.db.models.
This file is kept for backwards compatibility but can be removed.
"""

from h_arcane.db.models import CriterionResult, Evaluation, TaskEvaluationResult

__all__ = ["CriterionResult", "Evaluation", "TaskEvaluationResult"]
