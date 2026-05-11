from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from ergon_core.api.registry import ComponentRegistry
from ergon_core.core.application.components.catalog import ComponentCatalogService


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_register_builtins_can_publish_component_refs() -> None:
    from ergon_builtins.registry import register_builtins

    service = ComponentCatalogService()
    registry = ComponentRegistry(catalog_service=service)
    register_builtins(registry)
    session = _session()

    registry.publish(session)
    session.commit()

    ref = service.require(session, kind="worker", slug="training-stub")
    assert ref.module.endswith("training_stub_worker")
    assert ref.qualname == "TrainingStubWorker"
