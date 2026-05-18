"""Public benchmark ABC."""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from ergon_core.api.benchmark.task import EmptyTaskPayload, Task
from ergon_core.api.errors import DependencyError
from ergon_core.core.infrastructure.dependencies import check_packages
from pydantic import BaseModel


class Benchmark(ABC):
    """Base class for all benchmarks."""

    type_slug: ClassVar[str]
    task_payload_model: ClassVar[type[BaseModel]] = EmptyTaskPayload
    required_packages: ClassVar[list[str]] = []
    install_hint: ClassVar[str] = ""

    def __init__(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        metadata: Mapping[
            str,
            Any,  # slopcop: ignore[no-typing-any] -- public metadata bag accepts arbitrary JSON-like values # TODO: turn off slopcop for core package public api and remove all the slopcop ignores
        ]
        | None = None,
        created_by: str | None = None,
    ) -> None:
        self.name = name or self.__class__.__name__
        self.description = description or ""
        self.metadata: dict[
            str,
            Any,  # slopcop: ignore[no-typing-any] -- preserves caller-supplied benchmark metadata values
        ] = dict(metadata or {})
        # `created_by` deliberately preserves `None` as the unset sentinel,
        # unlike `name`/`description` which collapse to defaults via `or`.
        # Attribution wants the absent state distinguishable from empty
        # (an empty string would mean "explicitly set to nothing", which is
        # meaningless for "who created this").
        self.created_by = created_by

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
