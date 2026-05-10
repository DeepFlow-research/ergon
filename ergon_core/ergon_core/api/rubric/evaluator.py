"""Public advanced evaluator ABC."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, Field, field_validator

from ergon_core.api._definition import DefinitionModelMixin, import_component_string
from ergon_core.api.criterion.results import CriterionOutcome
from ergon_core.api.errors import DependencyError
from ergon_core.api.rubric.results import TaskEvaluationResult
from ergon_core.core.infrastructure.dependencies import check_packages

if TYPE_CHECKING:
    from ergon_core.api.benchmark.task import Task
    from ergon_core.api.criterion.criterion import Criterion
    from ergon_core.api.sandbox import Sandbox


class Evaluator(DefinitionModelMixin, BaseModel, ABC):
    """Base class for custom dynamic evaluators."""

    model_config = {"arbitrary_types_allowed": True, "extra": "allow", "frozen": False}

    type_slug: ClassVar[str]
    required_packages: ClassVar[list[str]] = []
    install_hint: ClassVar[str] = ""
    requires_sandbox: ClassVar[type[Sandbox] | None] = None

    name: str
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]

    def __init__(
        self,
        *,
        name: str,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
        **data: Any,  # slopcop: ignore[no-typing-any]
    ) -> None:
        super().__init__(name=name, metadata=dict(metadata or {}), **data)

    @field_validator("criteria", mode="before", check_fields=False)
    @classmethod
    def _inflate_criteria(cls, value: Any) -> Any:  # slopcop: ignore[no-typing-any]
        if isinstance(value, (list, tuple)):
            return tuple(_inflate_criterion_value(item) for item in value)
        return value

    @classmethod
    def from_definition(
        cls,
        evaluator_json: dict[str, Any],  # slopcop: ignore[no-typing-any]
    ) -> "Evaluator":
        """Reconstruct a concrete evaluator from persisted definition JSON."""
        evaluator_cls = import_component_string(evaluator_json["_type"])
        data = dict(evaluator_json)
        data.pop("_type", None)
        return evaluator_cls.model_validate(data)

    @abstractmethod
    def criteria_for(self, task: Task) -> Iterable[Criterion]:
        """Resolve the criterion set to run for *task*."""
        ...

    @abstractmethod
    def aggregate_task(
        self,
        task: Task,
        criterion_results: Iterable[CriterionOutcome],
    ) -> TaskEvaluationResult:
        """Aggregate criterion-level outputs into one task-level result."""
        ...

    def validate(self) -> None:
        """Check that runtime dependencies are available."""
        errors = check_packages(
            self.required_packages,
            f"Evaluator '{self.type_slug}'",
        )
        if errors:
            parts = [*errors]
            if self.install_hint:
                parts.append(f"Install with: {self.install_hint}")
            raise DependencyError("\n".join(parts))


def _is_definition(value: object) -> bool:
    return isinstance(value, dict) and "_type" in value


def _inflate_criterion_value(value: Any) -> Any:  # slopcop: ignore[no-typing-any]
    if isinstance(value, dict) and "criterion" in value:
        from ergon_core.api.rubric.rubric import WeightedCriterion

        return WeightedCriterion.model_validate(value)
    if _is_definition(value):
        from ergon_core.api.criterion.criterion import Criterion

        return Criterion.from_definition(value)
    return value
