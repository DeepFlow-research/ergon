"""Public process-level component registry.

The registry maps stable slugs stored in experiment definitions back to the
Python classes/factories needed by runtime jobs. Packages such as
``ergon_builtins`` and test fixtures contribute components explicitly during
startup; ``ergon_core`` never imports those packages to discover components.
"""

from collections.abc import Callable, Mapping
from typing import TypeVar

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.rubric import Evaluator
from ergon_core.api.worker import Worker
from ergon_core.core.infrastructure.sandbox.manager import BaseSandboxManager
from pydantic import BaseModel, ConfigDict, Field

WorkerFactory = Callable[..., Worker]
T = TypeVar("T")


class ComponentRegistry(BaseModel):
    """Catalog of component types available in the current Python process."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    workers: dict[str, WorkerFactory] = Field(default_factory=dict)
    benchmarks: dict[str, type[Benchmark]] = Field(default_factory=dict)
    evaluators: dict[str, type[Evaluator]] = Field(default_factory=dict)
    sandbox_managers: dict[str, type[BaseSandboxManager]] = Field(default_factory=dict)

    def register_worker(self, slug: str, factory: WorkerFactory) -> None:
        self._register(self.workers, "worker", slug, factory)

    def register_benchmark(self, benchmark_cls: type[Benchmark], slug: str | None = None) -> None:
        self._register(self.benchmarks, "benchmark", slug or benchmark_cls.type_slug, benchmark_cls)

    def register_evaluator(self, evaluator_cls: type[Evaluator], slug: str | None = None) -> None:
        self._register(self.evaluators, "evaluator", slug or evaluator_cls.type_slug, evaluator_cls)

    def register_sandbox_manager(
        self,
        slug: str,
        manager_cls: type[BaseSandboxManager],
    ) -> None:
        self._register(self.sandbox_managers, "sandbox manager", slug, manager_cls)

    def require_worker(self, slug: str) -> WorkerFactory:
        return self._require(self.workers, "worker", slug)

    def require_benchmark(self, slug: str) -> type[Benchmark]:
        return self._require(self.benchmarks, "benchmark", slug)

    def require_evaluator(self, slug: str) -> type[Evaluator]:
        return self._require(self.evaluators, "evaluator", slug)

    def _register(self, target: dict[str, T], kind: str, slug: str, value: T) -> None:
        existing = target.get(slug)
        if existing is not None and existing is not value:
            raise ValueError(f"Duplicate {kind} slug {slug!r}")
        target[slug] = value

    def _require(self, target: Mapping[str, T], kind: str, slug: str) -> T:
        try:
            return target[slug]
        except KeyError:
            known = ", ".join(sorted(target)) or "<none>"
            raise ValueError(
                f"Unknown {kind} slug {slug!r}; registered {kind}s: {known}"
            ) from None


registry = ComponentRegistry()
