"""Result types for evaluation Inngest functions.

These are the typed return values for evaluation-related Inngest functions.
"""

from uuid import UUID

from pydantic import BaseModel


class EvaluatorsResult(BaseModel):
    """Result of check_and_run_evaluators function."""

    task_id: UUID
    evaluators_found: int
    evaluators_run: int
    scores: list[float]
