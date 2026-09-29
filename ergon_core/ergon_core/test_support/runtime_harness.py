"""An in-memory graph runtime for unit tests.

``runtime_harness`` gives a test a SQLite session, a sample with one running
parent task, and the real ``TaskManagementService`` wired to that session, with
dashboard publishing and Inngest sends stubbed out. It backs the ``graph_runtime``
fixtures in ``ergon_core`` and ``ergon_builtins`` tests.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import TYPE_CHECKING, NamedTuple
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from ergon_core.api.task import Task
from ergon_core.api.worker.results import SpawnedTaskHandle
from ergon_core.core.application.runtime import management as management_module
from ergon_core.core.application.runtime import task_management as task_management_module
from ergon_core.core.application.runtime.lifecycle import on_task_completed_or_failed
from ergon_core.core.application.runtime.task_management import TaskManagementService
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.shared.enums import SampleStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord
from ergon_core.test_support.task_factory import TestSandbox, TestWorker
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

if TYPE_CHECKING:
    import pytest


class SessionContext:
    """A context manager that yields one existing session, for ``get_session`` patches."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *args: object) -> None:
        return None


def make_session() -> Session:
    """A session on a fresh in-memory SQLite database with every table created."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def seed_parent(session: Session, *, sample_id: UUID) -> SampleGraphNode:
    """Create an executing sample with one running root task, and return that task."""
    session.add(
        SampleRecord(
            id=sample_id,
            benchmark_type="test",
            instance_key="sample-1",
            worker_team_json={},
            status=SampleStatus.EXECUTING,
        )
    )
    parent = SampleGraphNode(
        sample_id=sample_id,
        instance_key="sample-1",
        task_slug="parent",
        description="Parent task",
        status="RUNNING",
        is_dynamic=False,
        parent_task_id=None,
        level=0,
    )
    session.add(parent)
    session.commit()
    return parent


def make_task(slug: str = "child") -> Task:
    """A minimal task a test can spawn."""
    return Task(
        task_slug=slug,
        instance_key="sample-1",
        description="spawned child",
        worker=TestWorker(name="worker", model="test:none"),
        sandbox=TestSandbox(),
        evaluators=(),
    )


def task_service(session: Session, monkeypatch: "pytest.MonkeyPatch") -> TaskManagementService:
    """A ``TaskManagementService`` whose ``get_session`` returns ``session``."""
    monkeypatch.setattr(management_module, "get_session", lambda: SessionContext(session))
    return TaskManagementService(
        dashboard_emitter=SimpleNamespace(graph_mutation=AsyncMock()),
        task_ready_dispatcher=AsyncMock(),
    )


class RuntimeHarness(NamedTuple):
    """A seeded sample and the task service around it."""

    session: Session
    sample_id: UUID
    parent: SampleGraphNode
    service: TaskManagementService

    async def spawn(
        self, slug: str, *, deps: tuple[UUID, ...] = (), actor: str | None = None
    ) -> SpawnedTaskHandle:
        """Spawn a child of the parent task, optionally bound to a named actor."""
        task = make_task(slug)
        if actor:
            task.worker.name = actor
            task.worker.actor_key = actor
            task.worker.metadata = {"actor_key": actor, "actor_role": "environment"}
        return await self.service.spawn_dynamic_task(
            sample_id=self.sample_id, parent_task_id=self.parent.task_id, task=task, depends_on=deps
        )

    def node(self, task_id: UUID) -> SampleGraphNode:
        """The graph row for ``task_id``."""
        node = self.session.get(SampleGraphNode, (self.sample_id, task_id))
        if node is None:
            raise LookupError(f"No graph node {task_id}")
        return node

    async def complete(self, task_id: UUID) -> list[UUID]:
        """Mark ``task_id`` completed and return the tasks that became ready."""
        self.node(task_id).status = "completed"
        self.session.commit()
        return await on_task_completed_or_failed(
            self.session,
            sample_id=self.sample_id,
            task_id=task_id,
            terminal_status="completed",
            graph_repo=self.service._graph_repo,
        )


@contextmanager
def runtime_harness(monkeypatch: "pytest.MonkeyPatch") -> Iterator[RuntimeHarness]:
    """Yield a ``RuntimeHarness`` and close its session afterwards."""
    session = make_session()
    sample_id = uuid4()
    parent = seed_parent(session, sample_id=sample_id)
    service = task_service(session, monkeypatch)
    monkeypatch.setattr(
        task_management_module,
        "get_dashboard_event_publisher",
        lambda: SimpleNamespace(publish=AsyncMock()),
    )
    monkeypatch.setattr(task_management_module.inngest_client, "send", AsyncMock())
    try:
        yield RuntimeHarness(session, sample_id, parent, service)
    finally:
        session.close()
