"""Public criterion ABC."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, ClassVar

from h_arcane.api.evaluation_context import EvaluationContext
from h_arcane.api.results import CriterionResult


class Criterion(ABC):
    """Atomic evaluation unit that owns its own data-pulling and verification logic.

    Subclasses must set ``type_slug`` and implement ``evaluate``.
    """

    type_slug: ClassVar[str]

    def __init__(
        self,
        *,
        name: str,
        weight: float = 1.0,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.weight = weight
        self.metadata: dict[str, Any] = dict(metadata or {})

    @abstractmethod
    async def evaluate(
        self,
        context: EvaluationContext,
    ) -> CriterionResult:
        """Run one atomic evaluation against the provided context."""
        ...

    def validate(self) -> None:
        """Cheap validation of criterion configuration."""
