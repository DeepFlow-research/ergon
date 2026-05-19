"""Application service for trusted component catalog references."""

from importlib import import_module
from typing import Any, Literal

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.rubric import Evaluator
from ergon_core.api.worker import Worker
from ergon_core.core.persistence.components.models import ComponentCatalogEntry
from ergon_core.core.shared.json_types import JsonObject
from ergon_core.core.shared.utils import utcnow
from ergon_core.core.infrastructure.sandbox.manager import BaseSandboxManager
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

ComponentKind = Literal["worker", "benchmark", "evaluator", "sandbox_manager", "model_backend"]


# TODO: move into models.py; add unit-test coverage.
class ComponentRef(BaseModel):
    """Importable reference for a registered component."""

    model_config = ConfigDict(frozen=True)

    kind: ComponentKind
    slug: str
    module: str
    qualname: str
    package: str | None = None
    version: str | None = None
    metadata: JsonObject = Field(default_factory=dict)


class ComponentCatalogService:
    """CRUD and import-ref lookup for the persistent component catalog."""

    def upsert(self, session: Session, ref: ComponentRef) -> ComponentCatalogEntry:
        row = session.exec(
            select(ComponentCatalogEntry).where(
                ComponentCatalogEntry.kind == ref.kind,
                ComponentCatalogEntry.slug == ref.slug,
            )
        ).one_or_none()

        if row is None:
            row = ComponentCatalogEntry(
                kind=ref.kind,
                slug=ref.slug,
                module=ref.module,
                qualname=ref.qualname,
            )

        row.module = ref.module
        row.qualname = ref.qualname
        row.package = ref.package
        row.version = ref.version
        row.metadata_json = dict(ref.metadata)
        row.updated_at = utcnow()
        session.add(row)
        return row

    def require(self, session: Session, *, kind: ComponentKind, slug: str) -> ComponentRef:
        row = session.exec(
            select(ComponentCatalogEntry).where(
                ComponentCatalogEntry.kind == kind,
                ComponentCatalogEntry.slug == slug,
            )
        ).one_or_none()
        if row is None:
            raise ValueError(f"Unknown {kind} component slug {slug!r}")
        return _row_to_ref(row)

    def load_ref(self, ref: ComponentRef) -> Any:  # slopcop: ignore[no-typing-any]
        return import_component_ref(ref)

    def build_worker(
        self,
        session: Session,
        *,
        slug: str,
        name: str,
        model: str | None,
    ) -> Worker:
        ref = self.require(session, kind="worker", slug=slug)
        worker_cls = self.load_ref(ref)
        if not isinstance(worker_cls, type) or not issubclass(worker_cls, Worker):
            raise TypeError(
                f"Worker component {slug!r} resolved to {worker_cls!r}, expected a Worker subclass"
            )
        return worker_cls(
            name=name,
            model=model,
            metadata=ref.metadata,
        )

    # TODO: this method is completely dead from what I can see atm. after PR 11, we should write an ast parser to catch all dead methods to figure out what to do with them all.
    def resolve_benchmark(
        self, session: Session, slug: str
    ) -> type[Benchmark]:  # TODO: consider if this should be a classmethod
        component = self.load_ref(self.require(session, kind="benchmark", slug=slug))
        if not isinstance(component, type) or not issubclass(component, Benchmark):
            # TODO: consider if we should have a more specific error type for this or if typeerror is fine
            raise TypeError(
                f"Benchmark component {slug!r} resolved to {component!r}, "
                "expected a Benchmark subclass"
            )
        return component

    def resolve_evaluator(self, session: Session, slug: str) -> type[Evaluator]:
        component = self.load_ref(self.require(session, kind="evaluator", slug=slug))
        if not isinstance(component, type) or not issubclass(component, Evaluator):
            # TODO: consider if we should have a more specific error type for this or if typeerror is fine
            raise TypeError(
                f"Evaluator component {slug!r} resolved to {component!r}, "
                "expected an Evaluator subclass"
            )
        return component

    def resolve_sandbox_manager(self, session: Session, slug: str) -> type[BaseSandboxManager]:
        component = self.load_ref(self.require(session, kind="sandbox_manager", slug=slug))
        if not isinstance(component, type) or not issubclass(component, BaseSandboxManager):
            # TODO: consider if we should have a more specific error type for this or if typeerror is fine
            raise TypeError(
                f"Sandbox manager component {slug!r} resolved to {component!r}, "
                "expected a BaseSandboxManager subclass"
            )
        return component


# TODO: just inline this logic on the class
def import_component_ref(ref: ComponentRef) -> Any:  # slopcop: ignore[no-typing-any]
    """Import the Python object referenced by a catalog row."""

    target: Any = import_module(ref.module)  # slopcop: ignore[no-typing-any]
    for part in ref.qualname.split("."):
        target = vars(target)[part]
    return target


# TODO: just inline this logic on the class
def _row_to_ref(row: ComponentCatalogEntry) -> ComponentRef:
    return ComponentRef(
        kind=row.kind,  # type: ignore[arg-type]
        slug=row.slug,
        module=row.module,
        qualname=row.qualname,
        package=row.package,
        version=row.version,
        metadata=row.parsed_metadata(),
    )
