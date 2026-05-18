"""Public criterion ABC."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

from ergon_core.api._serialization import TaskDefinitionJson, import_component_subclass
from ergon_core.api.criterion.context import CriterionContext
from ergon_core.api.criterion.results import CriterionOutcome, ScoreScale
from ergon_core.api.errors import DependencyError
from ergon_core.core.infrastructure.dependencies import check_packages


class Criterion(BaseModel, ABC):
    """Atomic evaluation unit that owns its own data-pulling and verification logic.

    PR 10 Task 0 converts ``Criterion`` from a hand-rolled ABC to a Pydantic
    ``BaseModel + ABC`` so concrete criterion instances can be serialized into
    ``task_json`` snapshots alongside ``Task``, ``Worker``, ``Sandbox``, and
    ``Evaluator``. Concrete subclasses declare per-instance configuration as
    Pydantic fields; ``type_slug`` / ``required_packages`` / ``install_hint``
    stay as ``ClassVar`` so Pydantic leaves them alone.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        frozen=False,
        extra="allow",
    )

    type_slug: ClassVar[str]
    required_packages: ClassVar[list[str]] = []
    install_hint: ClassVar[str] = ""

    slug: str
    description: str = ""  # slopcop: ignore[no-str-empty-default]
    weight: float = 1.0
    score_spec: ScoreScale = Field(default_factory=ScoreScale)
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]

    @model_validator(mode="after")
    def _default_description_to_slug(self) -> "Criterion":
        """Preserve v1 behavior: if description is empty, fall back to slug."""
        if not self.description:
            object.__setattr__(self, "description", self.slug)
        return self

    @model_serializer(mode="wrap")
    def _serialize_with_type_discriminator(
        self,
        handler: Callable[["Criterion"], dict[str, Any]],  # slopcop: ignore[no-typing-any]
    ) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
        """Inject ``_type`` so criterion snapshots can round-trip."""
        payload = handler(self)
        payload["_type"] = f"{type(self).__module__}:{type(self).__qualname__}"
        return payload

    @classmethod
    def from_definition(cls, criterion_json: TaskDefinitionJson) -> "Criterion":
        """Reconstruct a Criterion subclass from ``_type``-discriminated JSON."""

        criterion_type = criterion_json.get("_type")
        if not isinstance(criterion_type, str):
            raise ValueError(
                f"Criterion snapshot is missing the required `_type` discriminator "
                f"(got {type(criterion_type).__name__}). Every persisted criterion "
                f"must carry `_type`."
            )
        CriterionCls = import_component_subclass(criterion_type, Criterion, kind="Criterion")
        payload = {k: v for k, v in criterion_json.items() if k != "_type"}
        return cast("Criterion", CriterionCls.model_validate(payload))

    @abstractmethod
    async def evaluate(
        self,
        context: CriterionContext,
    ) -> CriterionOutcome:
        """Run one atomic evaluation against the provided context."""
        ...

    def validate(self) -> None:  # ty: ignore[invalid-method-override]
        """Check that runtime dependencies are available.

        Shadows the deprecated ``BaseModel.validate`` classmethod alias
        intentionally — Criterion semantics predate the Pydantic conversion
        and ``criterion.validate()`` is the public API every benchmark uses.
        ``Evaluator`` solved the same collision by renaming to
        ``validate_runtime_deps``; we keep the legacy name here to avoid
        churning every benchmark in PR 10 Task 0.
        """
        errors = check_packages(
            self.required_packages,
            f"Criterion '{self.type_slug}'",
        )
        if errors:
            parts = [*errors]
            if self.install_hint:
                parts.append(f"Install with: {self.install_hint}")
            raise DependencyError("\n".join(parts))
