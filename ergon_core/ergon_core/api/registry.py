"""Process-local component catalog used by CLI and test harnesses."""

from collections.abc import Mapping
from typing import Literal, TypeVar, cast

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.rubric import Evaluator
from ergon_core.api.worker import Worker
from ergon_core.core.infrastructure.sandbox.manager import BaseSandboxManager
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

ComponentKind = Literal["worker", "benchmark", "evaluator", "sandbox_manager"]
T = TypeVar("T")


class ComponentCatalog(BaseModel):
    """Catalog of component types available in the current Python process."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    workers: dict[str, type[Worker]] = Field(default_factory=dict)
    benchmarks: dict[str, type[Benchmark]] = Field(default_factory=dict)
    evaluators: dict[str, type[Evaluator]] = Field(default_factory=dict)
    sandbox_managers: dict[str, type[BaseSandboxManager]] = Field(default_factory=dict)

    def register_worker(self, slug: str, worker_cls: type[Worker]) -> None:
        self._register(self.workers, "worker", slug, worker_cls)

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

    def require_worker(self, slug: str) -> type[Worker]:
        return self._require(self.workers, "worker", slug)

    def require_benchmark(self, slug: str) -> type[Benchmark]:
        return self._require(self.benchmarks, "benchmark", slug)

    def require_evaluator(self, slug: str) -> type[Evaluator]:
        return self._require(self.evaluators, "evaluator", slug)

    def deregister(self, kind: ComponentKind, slug: str) -> None:
        self._mapping_for(kind).pop(slug, None)

    def publish(self, session: Session) -> None:
        del session

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
            raise ValueError(f"Unknown {kind} slug {slug!r}; registered {kind}s: {known}") from None

    def _mapping_for(self, kind: ComponentKind) -> dict[str, object]:
        if kind == "worker":
            return cast(dict[str, object], self.workers)
        if kind == "benchmark":
            return cast(dict[str, object], self.benchmarks)
        if kind == "evaluator":
            return cast(dict[str, object], self.evaluators)
        if kind == "sandbox_manager":
            return cast(dict[str, object], self.sandbox_managers)
        raise ValueError(f"Unsupported component kind {kind!r}")


registry = ComponentCatalog()
