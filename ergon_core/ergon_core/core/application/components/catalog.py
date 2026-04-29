"""Application boundary for the persistent component catalog."""

from importlib import import_module
from typing import Any, Literal

from ergon_core.core.persistence.components.models import ComponentCatalogEntry
from ergon_core.core.shared.json_types import JsonObject
from ergon_core.core.shared.utils import utcnow as _utcnow
from pydantic import BaseModel, Field
from sqlmodel import Session, select

ComponentKind = Literal["worker", "benchmark", "evaluator", "sandbox_manager", "model_backend"]


class ComponentRef(BaseModel):
    """Importable reference for a registered component."""

    kind: ComponentKind
    slug: str
    module: str
    qualname: str
    package: str | None = None
    version: str | None = None
    metadata: JsonObject = Field(default_factory=dict)


class ComponentCatalogService:
    """Publish and require component import refs."""

    def upsert(self, session: Session, ref: ComponentRef) -> ComponentCatalogEntry:
        statement = select(ComponentCatalogEntry).where(
            ComponentCatalogEntry.kind == ref.kind,
            ComponentCatalogEntry.slug == ref.slug,
        )
        entry = session.exec(statement).first()
        if entry is None:
            entry = ComponentCatalogEntry(
                kind=ref.kind,
                slug=ref.slug,
                module=ref.module,
                qualname=ref.qualname,
                package=ref.package,
                version=ref.version,
                metadata_json=dict(ref.metadata),
            )
            session.add(entry)
            return entry

        entry.module = ref.module
        entry.qualname = ref.qualname
        entry.package = ref.package
        entry.version = ref.version
        entry.metadata_json = dict(ref.metadata)
        entry.updated_at = _utcnow()
        return entry

    def require(self, session: Session, *, kind: ComponentKind, slug: str) -> ComponentRef:
        statement = select(ComponentCatalogEntry).where(
            ComponentCatalogEntry.kind == kind,
            ComponentCatalogEntry.slug == slug,
        )
        entry = session.exec(statement).first()
        if entry is None:
            raise ValueError(f"Unknown {kind} component slug {slug!r}")
        return ComponentRef(
            kind=entry.kind,  # type: ignore[arg-type]
            slug=entry.slug,
            module=entry.module,
            qualname=entry.qualname,
            package=entry.package,
            version=entry.version,
            metadata=entry.parsed_metadata(),
        )


def import_component_ref(ref: ComponentRef) -> Any:  # slopcop: ignore[no-typing-any]
    """Import the Python object referenced by a catalog row."""

    target: Any = import_module(ref.module)  # slopcop: ignore[no-typing-any]
    for part in ref.qualname.split("."):
        target = getattr(target, part)
    return target
"""Application service for trusted component catalog references."""

from importlib import import_module
from typing import Any

from ergon_core.core.persistence.components.models import ComponentCatalogEntry
from ergon_core.core.shared.json_types import JsonObject
from ergon_core.core.shared.utils import utcnow
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select


class ComponentRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str
    slug: str
    module: str
    qualname: str
    package: str | None = None
    version: str | None = None
    metadata: JsonObject = Field(default_factory=dict)


class ComponentCatalogService:
    def upsert(self, session: Session, ref: ComponentRef) -> ComponentCatalogEntry:
        existing = session.exec(
            select(ComponentCatalogEntry).where(
                ComponentCatalogEntry.kind == ref.kind,
                ComponentCatalogEntry.slug == ref.slug,
            )
        ).one_or_none()

        row = existing or ComponentCatalogEntry(
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

    def require(self, session: Session, *, kind: str, slug: str) -> ComponentRef:
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


def import_component_ref(ref: ComponentRef) -> Any:  # slopcop: ignore[no-typing-any]
    target: Any = import_module(ref.module)  # slopcop: ignore[no-typing-any]
    for part in ref.qualname.split("."):
        target = getattr(target, part)
    return target


def _row_to_ref(row: ComponentCatalogEntry) -> ComponentRef:
    return ComponentRef(
        kind=row.kind,
        slug=row.slug,
        module=row.module,
        qualname=row.qualname,
        package=row.package,
        version=row.version,
        metadata=row.parsed_metadata(),
    )
