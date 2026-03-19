"""Base class for evaluation criteria."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from h_arcane.core._internal.db.models import CriterionResult
    from h_arcane.core._internal.evaluation.runtime import CriterionRuntime
    from h_arcane.core._internal.evaluation.schemas import CriterionContext


class BaseCriterion(BaseModel, ABC):
    """Base class for all evaluation criteria."""

    name: str = Field(description="Short name for this criterion")
    description: str = Field(description="What this rule evaluates")
    weight: float = Field(
        default=1.0,
        ge=0.0,
        description="Relative importance (non-negative)",
    )

    @abstractmethod
    async def evaluate(
        self,
        runtime: "CriterionRuntime",
        context: "CriterionContext",
    ) -> "CriterionResult":
        """Evaluate this criterion using the provided runtime + context.

        Args:
            runtime: Criterion runtime providing execution helpers
            context: Criterion-specific evaluation context

        Returns:
            CriterionResult with score, feedback, and evaluated references
        """
        ...


# Backwards-compatible alias while internal naming migrates.
BaseRule = BaseCriterion
