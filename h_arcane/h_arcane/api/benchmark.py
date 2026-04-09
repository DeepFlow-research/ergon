"""Public benchmark ABC.

Uses ABCs (not Protocols) for discoverability via isinstance, template-method
helpers, and the HuggingFace "real classes" authoring feel. type_slug is
ClassVar because it identifies the CLASS for registry lookup and definition
persistence -- not a per-instance property.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from h_arcane.api.task_types import BenchmarkTask


class Benchmark(ABC):
    """Base class for all benchmarks.

    Subclasses must set ``type_slug`` and implement ``build_instances``.
    """

    type_slug: ClassVar[str]

    def __init__(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
    ) -> None:
        self.name = name or self.__class__.__name__
        self.description = description or ""
        self.metadata: dict[str, Any] = dict(metadata or {})  # slopcop: ignore[no-typing-any]

    @abstractmethod
    def build_instances(self) -> Mapping[str, Sequence[BenchmarkTask]]:
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

    def validate(self) -> None:
        """Cheap validation of benchmark configuration."""
