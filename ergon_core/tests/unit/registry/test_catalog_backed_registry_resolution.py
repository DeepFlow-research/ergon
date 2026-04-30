from collections.abc import AsyncGenerator

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from ergon_core.api.benchmark import Task
from ergon_core.api.worker import Worker, WorkerContext, WorkerOutput
from ergon_core.api.worker.worker import WorkerStreamItem
from ergon_core.core.application.components.catalog import ComponentCatalogService, ComponentRef


class CatalogSmokeWorker(Worker):
    type_slug = "catalog-smoke-worker"

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        yield WorkerOutput(output="ok", success=True)


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_build_worker_imports_worker_class_without_local_registration() -> None:
    session = _session()
    service = ComponentCatalogService()
    service.upsert(
        session,
        ComponentRef(
            kind="worker",
            slug=CatalogSmokeWorker.type_slug,
            module=__name__,
            qualname="CatalogSmokeWorker",
        ),
    )
    session.commit()

    loaded = service.build_worker(
        session,
        slug=CatalogSmokeWorker.type_slug,
        name="primary",
        model="stub:constant",
    )

    assert isinstance(loaded, CatalogSmokeWorker)
    assert loaded.name == "primary"
