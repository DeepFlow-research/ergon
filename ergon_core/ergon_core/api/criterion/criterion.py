"""Public criterion ABC."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, Field

from ergon_core.api.criterion.results import CriterionOutcome
from ergon_core.api.errors import DependencyError
from ergon_core.core.domain.definitions import inflate_definition, serialize_definition
from ergon_core.core.infrastructure.dependencies import check_packages
from ergon_core.core.shared.json_types import JsonObject

if TYPE_CHECKING:
    from ergon_core.api.criterion.context import CriterionContext
    from ergon_core.api.sandbox import Sandbox


class Criterion(BaseModel, ABC):
    """Atomic evaluation unit that owns its own data-pulling and verification logic."""

    model_config = {"arbitrary_types_allowed": True, "extra": "allow", "frozen": False}

    type_slug: ClassVar[str]
    required_packages: ClassVar[list[str]] = []
    install_hint: ClassVar[str]
    requires_sandbox: ClassVar[type[Sandbox] | None] = None

    slug: str
    description: str = ""  # slopcop: ignore[no-str-empty-default]
    metadata: JsonObject = Field(default_factory=dict)

    @classmethod
    def from_definition(
        cls,
        criterion_json: JsonObject,
    ) -> "Criterion":
        """Reconstruct a concrete criterion from persisted definition JSON."""
        return inflate_definition(criterion_json)

    def to_definition(self) -> JsonObject:
        """Serialize this criterion for persisted experiment definitions."""
        return serialize_definition(self)

    @abstractmethod
    async def evaluate(
        self,
        context: CriterionContext,
        *,
        sandbox: Sandbox,
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
