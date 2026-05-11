"""Public criterion ABC."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, Field

from ergon_core.api._definition import from_definition_dict, to_definition_dict
from ergon_core.api.criterion.results import CriterionOutcome, ScoreScale
from ergon_core.api.errors import DependencyError
from ergon_core.core.infrastructure.dependencies import check_packages

if TYPE_CHECKING:
    from ergon_core.api.criterion.context import CriterionContext
    from ergon_core.api.sandbox import Sandbox


class Criterion(BaseModel, ABC):
    """Atomic evaluation unit that owns its own data-pulling and verification logic."""

    model_config = {"arbitrary_types_allowed": True, "extra": "allow", "frozen": False}

    type_slug: ClassVar[str]
    required_packages: ClassVar[list[str]] = []
    install_hint: ClassVar[str] = ""
    requires_sandbox: ClassVar[type[Sandbox] | None] = None

    slug: str
    description: str
    weight: float = 1.0
    score_spec: ScoreScale = Field(default_factory=ScoreScale)
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]

    def __init__(
        self,
        *,
        slug: str,
        description: str | None = None,
        weight: float = 1.0,
        score_spec: ScoreScale | None = None,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
        **data: Any,  # slopcop: ignore[no-typing-any]
    ) -> None:
        super().__init__(
            slug=slug,
            description=description or slug,
            weight=weight,
            score_spec=score_spec or ScoreScale(),
            metadata=dict(metadata or {}),
            **data,
        )

    @classmethod
    def from_definition(
        cls,
        criterion_json: dict[str, Any],  # slopcop: ignore[no-typing-any]
    ) -> "Criterion":
        """Reconstruct a concrete criterion from persisted definition JSON."""
        return from_definition_dict(criterion_json)

    def to_definition(self) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
        """Serialize this criterion for persisted experiment definitions."""
        return to_definition_dict(self)

    @abstractmethod
    async def evaluate(
        self,
        context: CriterionContext,
    ) -> CriterionOutcome:
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
