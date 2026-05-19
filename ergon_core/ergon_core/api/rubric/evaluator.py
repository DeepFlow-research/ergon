"""Public ``Evaluator`` ABC (Pydantic BaseModel) for v2 object-bound benchmarks."""

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from typing import Any, ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from ergon_core.api._serialization import TaskDefinitionJson, import_component_subclass
from ergon_core.api.benchmark.task import Task
from ergon_core.api.criterion.criterion import Criterion
from ergon_core.api.criterion.results import CriterionOutcome
from ergon_core.api.errors import DependencyError
from ergon_core.api.rubric.results import TaskEvaluationResult
from ergon_core.core.infrastructure.dependencies import check_packages


class Evaluator(BaseModel, ABC):
    """Base class for custom dynamic evaluators. Pydantic-serializable.

    PR 5 converts the v1 hand-rolled ABC to a Pydantic ``BaseModel``
    so evaluators round-trip through ``task_json`` snapshots alongside
    ``Task``, ``Worker``, and ``Sandbox``. Concrete subclasses declare
    config fields directly on the model.

    ``type_slug`` / ``required_packages`` / ``install_hint`` are
    ``ClassVar``s on the subclass — Pydantic leaves ``ClassVar`` alone,
    so they don't become serialized fields.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        frozen=False,
        extra="allow",
    )

    type_slug: ClassVar[str]
    required_packages: ClassVar[list[str]] = []
    install_hint: ClassVar[str] = (
        ""  # TODO: this should not be "" default, make this just optional arg
    )

    name: str
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]

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

    @classmethod
    def from_definition(cls, evaluator_json: TaskDefinitionJson) -> "Evaluator":
        """Reconstruct an Evaluator subclass from ``_type``-discriminated JSON."""

        evaluator_type = evaluator_json.get("_type")
        if not isinstance(evaluator_type, str):
            raise ValueError(
                f"Evaluator snapshot is missing the required `_type` discriminator "
                f"(got {type(evaluator_type).__name__}). Every persisted evaluator "
                f"must carry `_type`."
            )
        EvaluatorCls = import_component_subclass(evaluator_type, Evaluator, kind="Evaluator")
        payload = {k: v for k, v in evaluator_json.items() if k != "_type"}
        return cast("Evaluator", EvaluatorCls.model_validate(payload))

    # TODO: check if this is ever actually used, if not delete it
    def validate_runtime_deps(self) -> None:
        """Check that runtime dependencies are available.

        Renamed from ``validate`` because Pydantic v2 reserves ``validate``
        on ``BaseModel``. Renaming also makes the intent (check importable
        packages) explicit at every call site.
        """
        errors = check_packages(
            self.required_packages,
            f"Evaluator '{self.type_slug}'",
        )
        if errors:
            parts = [*errors]
            if self.install_hint:
                parts.append(f"Install with: {self.install_hint}")
            raise DependencyError("\n".join(parts))

    @model_serializer(mode="wrap")
    def _serialize_with_type_discriminator(
        self,
        handler: Callable[["Evaluator"], dict[str, Any]],  # slopcop: ignore[no-typing-any]
    ) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
        """Inject the ``_type`` discriminator on every dump (mirrors ``Worker``)."""
        payload = handler(self)
        payload["_type"] = f"{type(self).__module__}:{type(self).__qualname__}"
        return payload
