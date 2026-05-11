"""Public benchmark ABC."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from pydantic import BaseModel, Field, field_validator

from ergon_core.api._definition import from_definition_dict, import_component_string, is_definition, to_definition_dict
from ergon_core.api.benchmark.task import EmptyTaskPayload, Task
from ergon_core.api.errors import DependencyError
from ergon_core.core.infrastructure.dependencies import check_packages


class Benchmark(BaseModel, ABC):
    """Base class for all benchmarks."""

    model_config = {"arbitrary_types_allowed": True, "extra": "allow", "frozen": False}

    type_slug: ClassVar[str]
    task_payload_model: ClassVar[type[BaseModel]] = EmptyTaskPayload
    required_packages: ClassVar[list[str]] = []
    install_hint: ClassVar[str]

    name: str
    description: str
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]

    def __init__(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        metadata: Mapping[
            str,
            Any,  # slopcop: ignore[no-typing-any] -- public metadata bag accepts arbitrary JSON-like values
        ]
        | None = None,
        **data: Any,  # slopcop: ignore[no-typing-any]
    ) -> None:
        super().__init__(
            name=name or self.__class__.__name__,
            description=description or "",
            metadata=dict(metadata or {}),
            **data,
        )

    @classmethod
    def from_definition(
        cls,
        benchmark_json: dict[str, Any],  # slopcop: ignore[no-typing-any]
    ) -> "Benchmark":
        """Reconstruct a concrete benchmark from persisted definition JSON."""
        benchmark_cls = import_component_string(benchmark_json["_type"])
        data = dict(benchmark_json)
        data.pop("_type", None)
        return benchmark_cls.model_validate(data)

    def to_definition(self) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
        """Serialize this benchmark for persisted experiment definitions."""
        return to_definition_dict(self)

    @abstractmethod
    def build_instances(self) -> Mapping[str, Sequence[Task[BaseModel]]]:
        """Materialize benchmark instances."""
        ...

    def evaluator_requirements(self) -> Sequence[str]:
        """Declare evaluator slot names required by this benchmark."""
        return ("default",)

    @classmethod
    def parse_task_payload(
        cls,
        payload: BaseModel
        | Mapping[
            str,
            Any,  # slopcop: ignore[no-typing-any] -- arbitrary persisted JSON is validated below
        ]
        | None,
    ) -> BaseModel:
        """Validate persisted JSON into this benchmark's payload model."""
        if payload is None:
            return cls.task_payload_model()
        if isinstance(payload, cls.task_payload_model):
            return payload
        if isinstance(payload, BaseModel):
            payload = payload.model_dump()
        return cls.task_payload_model.model_validate(payload)

    def validate(self) -> None:
        """Check that runtime dependencies are available."""
        errors = check_packages(
            self.required_packages,
            f"Benchmark '{self.type_slug}'",
        )
        if errors:
            parts = [*errors]
            if self.install_hint:
                parts.append(f"Install with: {self.install_hint}")
            raise DependencyError("\n".join(parts))

    @field_validator("tasks", mode="before", check_fields=False)
    @classmethod
    def _inflate_tasks(cls, value: Any) -> Any:  # slopcop: ignore[no-typing-any]
        if isinstance(value, (list, tuple)):
            return tuple(
                from_definition_dict(item) if is_definition(item) else item for item in value
            )
        return value
