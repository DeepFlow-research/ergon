"""Base class for evaluation rules."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from h_arcane.evaluation.context import EvaluationRunner
    from h_arcane.db.models import CriterionResult


class BaseRule(BaseModel, ABC):
    """Base class for all evaluation rules."""

    name: str = Field(description="Short name for this criterion")
    description: str = Field(description="What this rule evaluates")
    weight: float = Field(
        default=1.0,
        ge=0.0,
        description="Relative importance (non-negative)",
    )

    @abstractmethod
    async def evaluate(self, runner: "EvaluationRunner") -> "CriterionResult":
        """Evaluate this rule using the provided runner.

        Args:
            runner: EvaluationRunner providing data and infrastructure methods

        Returns:
            CriterionResult with score, feedback, and evaluated references
        """
        ...
