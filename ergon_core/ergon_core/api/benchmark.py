"""Public benchmark ABC.

Uses ABCs (not Protocols) for discoverability via isinstance, template-method
helpers, and the HuggingFace "real classes" authoring feel. type_slug is
ClassVar because it identifies the CLASS for registry lookup and definition
persistence -- not a per-instance property.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from ergon_core.api.benchmark_deps import BenchmarkDeps
from ergon_core.api.dependencies import check_packages
from ergon_core.api.errors import DependencyError
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.template_spec import NoSetupSentinel, TemplateSpec, _NoSetupType


class Benchmark(ABC):
    """Base class for all benchmarks.

    Subclasses MUST set ``type_slug``, ``onboarding_deps``, and
    ``template_spec``, and implement ``build_instances``.
    Omitting ``onboarding_deps`` or ``template_spec`` raises ``TypeError``
    at class definition time.
    """

    type_slug: ClassVar[str]
    onboarding_deps: ClassVar[BenchmarkDeps]
    template_spec: ClassVar[TemplateSpec | NoSetupSentinel]
    required_packages: ClassVar[list[str]] = []
    install_hint: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:  # slopcop: ignore[no-typing-any]
        super().__init_subclass__(**kwargs)
        # Only enforce on concrete classes (those that also define type_slug).
        # Abstract intermediate subclasses may omit the field.
        abstract = getattr(cls, "__abstractmethods__", None)  # slopcop: ignore[no-hasattr-getattr]
        has_slug = hasattr(cls, "type_slug")  # slopcop: ignore[no-hasattr-getattr]
        if not abstract and has_slug:
            deps = getattr(cls, "onboarding_deps", None)  # slopcop: ignore[no-hasattr-getattr]
            if not isinstance(deps, BenchmarkDeps):
                raise TypeError(
                    f"{cls.__qualname__} must declare "
                    f"'onboarding_deps: ClassVar[BenchmarkDeps] = BenchmarkDeps(...)'. "
                    f"See ergon_core/api/benchmark_deps.py."
                )
            spec = getattr(cls, "template_spec", None)  # slopcop: ignore[no-hasattr-getattr]
            if not isinstance(spec, (TemplateSpec, _NoSetupType)):
                raise TypeError(
                    f"{cls.__qualname__} must declare "
                    f"'template_spec: ClassVar[TemplateSpec | NoSetupSentinel]' "
                    f"set to either a TemplateSpec instance or NoSetup. "
                    f"See ergon_core/api/template_spec.py."
                )

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
