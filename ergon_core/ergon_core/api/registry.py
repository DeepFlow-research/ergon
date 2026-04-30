"""Public process-level component registry.

The registry maps stable slugs stored in experiment definitions back to the
Python classes/factories needed by runtime jobs. Packages such as
``ergon_builtins`` and test fixtures contribute components explicitly during
startup; ``ergon_core`` never imports those packages to discover components.
"""

from collections.abc import Mapping
from typing import TypeVar

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.rubric import Evaluator
from ergon_core.api.worker import Worker
from ergon_core.core.application.components.catalog import (
    ComponentCatalogService,
    ComponentKind,
    ComponentRef,
)
from ergon_core.core.infrastructure.sandbox.manager import BaseSandboxManager
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

T = TypeVar("T")


class ComponentRegistry(BaseModel):
    """Catalog of component types available in the current Python process."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    catalog_service: ComponentCatalogService
    component_refs: dict[tuple[str, str], ComponentRef] = Field(default_factory=dict)
    workers: dict[str, type[Worker]] = Field(default_factory=dict)
    benchmarks: dict[str, type[Benchmark]] = Field(default_factory=dict)
    evaluators: dict[str, type[Evaluator]] = Field(default_factory=dict)
    sandbox_managers: dict[str, type[BaseSandboxManager]] = Field(default_factory=dict)

    def register_worker(self, slug: str, worker_cls: type[Worker]) -> None:
        self._register(self.workers, "worker", slug, worker_cls)
        self._remember_ref("worker", slug, worker_cls)

    def register_benchmark(self, benchmark_cls: type[Benchmark], slug: str | None = None) -> None:
        resolved_slug = slug or benchmark_cls.type_slug
        self._register(self.benchmarks, "benchmark", resolved_slug, benchmark_cls)
        self._remember_ref("benchmark", resolved_slug, benchmark_cls)

    def register_evaluator(self, evaluator_cls: type[Evaluator], slug: str | None = None) -> None:
        resolved_slug = slug or evaluator_cls.type_slug
        self._register(self.evaluators, "evaluator", resolved_slug, evaluator_cls)
        self._remember_ref("evaluator", resolved_slug, evaluator_cls)

    def register_sandbox_manager(
        self,
        slug: str,
        manager_cls: type[BaseSandboxManager],
    ) -> None:
        self._register(self.sandbox_managers, "sandbox manager", slug, manager_cls)
        self._remember_ref("sandbox_manager", slug, manager_cls)

    def require_worker(self, slug: str) -> type[Worker]:
        return self._require(self.workers, "worker", slug)

    def require_benchmark(self, slug: str) -> type[Benchmark]:
        return self._require(self.benchmarks, "benchmark", slug)

    def require_evaluator(self, slug: str) -> type[Evaluator]:
        return self._require(self.evaluators, "evaluator", slug)

    def deregister(self, kind: ComponentKind, slug: str) -> None:
        self._mapping_for(kind).pop(slug, None)
        self.component_refs.pop((kind, slug), None)

    def publish(self, session: Session) -> None:
        for ref in self.component_refs.values():
            self.catalog_service.upsert(session, ref)

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
            return self.workers
        if kind == "benchmark":
            return self.benchmarks
        if kind == "evaluator":
            return self.evaluators
        if kind == "sandbox_manager":
            return self.sandbox_managers
        raise ValueError(f"Unsupported component kind {kind!r}")

    def _remember_ref(self, kind: ComponentKind, slug: str, value: object) -> None:
        module = getattr(value, "__module__", None)
        qualname = getattr(value, "__qualname__", None)
        if not isinstance(module, str) or not isinstance(qualname, str):
            raise ValueError(
                f"Cannot register {kind} slug {slug!r}: component must be an importable "
                "module-level object with __module__ and __qualname__."
            )
        self.component_refs[(kind, slug)] = ComponentRef(
            kind=kind,
            slug=slug,
            module=module,
            qualname=qualname,
        )


registry = ComponentRegistry(catalog_service=ComponentCatalogService())
