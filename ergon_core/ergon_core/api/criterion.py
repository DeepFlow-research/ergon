"""Public criterion ABC."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, ClassVar

from ergon_core.api.dependencies import check_packages
from ergon_core.api.errors import DependencyError
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.results import CriterionResult


class Criterion(ABC):
    """Atomic evaluation unit that owns its own data-pulling and verification logic.

    Subclasses must set ``type_slug`` and implement ``evaluate``.
    """

    type_slug: ClassVar[str]
    required_packages: ClassVar[list[str]] = []
    install_hint: ClassVar[str] = ""

    def __init__(
        self,
        *,
        name: str,
        weight: float = 1.0,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
    ) -> None:
        self.name = name
        self.weight = weight
        self.metadata: dict[str, Any] = dict(metadata or {})  # slopcop: ignore[no-typing-any]

    @abstractmethod
    async def evaluate(
        self,
        context: EvaluationContext,
    ) -> CriterionResult:
        """Run one atomic evaluation against the provided context."""
        ...

    def validate(self) -> None:
        """Check that runtime dependencies are available."""
        errors = check_packages(
            self.required_packages,
            f"Criterion '{self.type_slug}'",
        )
        if errors:
            parts = [*errors]
            if self.install_hint:
                parts.append(f"Install with: {self.install_hint}")
            raise DependencyError("\n".join(parts))
