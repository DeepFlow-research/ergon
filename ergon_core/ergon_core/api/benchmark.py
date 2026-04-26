"""Public benchmark ABC.

Uses ABCs (not Protocols) for discoverability via isinstance, template-method
helpers, and the HuggingFace "real classes" authoring feel. type_slug is
ClassVar because it identifies the CLASS for registry lookup and definition
persistence -- not a per-instance property.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from pydantic import BaseModel

from ergon_core.api.dependencies import check_packages
from ergon_core.api.errors import DependencyError
from ergon_core.api.task_types import BenchmarkTask, EmptyTaskPayload


class Benchmark(ABC):
    """Base class for all benchmarks.

    Subclasses MUST set ``type_slug`` and ``onboarding_deps`` and implement
    ``build_instances``.  Omitting ``onboarding_deps`` raises ``TypeError``
    at class definition time.
    """

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
            Any,  # slopcop: ignore[no-typing-any] -- public metadata bag accepts arbitrary JSON-like values
        ]
        | None = None,
    ) -> None:
        self.name = name or self.__class__.__name__
        self.description = description or ""
        self.metadata: dict[
            str,
            Any,  # slopcop: ignore[no-typing-any] -- preserves caller-supplied benchmark metadata values
        ] = dict(metadata or {})

    @abstractmethod
    def build_instances(self) -> Mapping[str, Sequence[BenchmarkTask[BaseModel]]]:
        """Materialize benchmark instances.

        Returns a mapping of instance_key -> tasks for that instance.
        """
        ...

    def evaluator_requirements(self) -> Sequence[str]:
        """Declare evaluator slot names required by this benchmark.

        Returns slot names (e.g. ``["default"]``) that ``Experiment.validate``
        checks are filled by the experiment's evaluator mapping.
        """
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
