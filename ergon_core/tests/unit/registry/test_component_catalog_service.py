import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from ergon_core.core.application.components.catalog import (
    ComponentCatalogService,
    ComponentRef,
    import_component_ref,
)
from ergon_core.core.persistence.components.models import ComponentCatalogEntry


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_upsert_and_require_component_ref() -> None:
    session = _session()
    service = ComponentCatalogService()

    service.upsert(
        session,
        ComponentRef(
            kind="worker",
            slug="training-stub",
            module="ergon_builtins.shared.workers.training_stub_worker",
            qualname="TrainingStubWorker",
            package="ergon-builtins",
            metadata={"install_hint": "none"},
        ),
    )
    session.commit()

    ref = service.require(session, kind="worker", slug="training-stub")
    assert ref.module == "ergon_builtins.shared.workers.training_stub_worker"
    assert ref.qualname == "TrainingStubWorker"
    assert ref.metadata == {"install_hint": "none"}


def test_upsert_updates_existing_ref() -> None:
    session = _session()
    service = ComponentCatalogService()

    service.upsert(session, ComponentRef(kind="worker", slug="x", module="old", qualname="Thing"))
    service.upsert(session, ComponentRef(kind="worker", slug="x", module="new", qualname="Other"))
    session.commit()

    rows = session.exec(select(ComponentCatalogEntry)).all()
    assert len(rows) == 1
    assert service.require(session, kind="worker", slug="x").module == "new"


def test_import_component_ref_imports_module_qualname() -> None:
    ref = ComponentRef(
        kind="worker",
        slug="component-ref",
        module="ergon_core.core.application.components.catalog",
        qualname="ComponentRef",
    )

    assert import_component_ref(ref) is ComponentRef


def test_require_unknown_component_lists_kind_and_slug() -> None:
    session = _session()

    with pytest.raises(ValueError, match="Unknown worker component slug 'missing'"):
        ComponentCatalogService().require(session, kind="worker", slug="missing")
