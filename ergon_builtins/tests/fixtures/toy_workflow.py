from collections.abc import AsyncGenerator
from typing import ClassVar
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ConfigDict
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select

from ergon_core.api import Sandbox, Task, Worker, WorkerContext, WorkerOutput, WorkerStreamItem
from ergon_core.core.application.runtime import management as management_module
from ergon_core.core.application.runtime.task_inspection import TaskInspectionService
from ergon_core.core.application.runtime.task_management import TaskManagementService
from ergon_core.core.persistence.definitions.models import ExperimentDefinitionTask
from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphNode
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import RunRecord


class ToySandbox(Sandbox):
    type_slug: ClassVar[str] = "toy-sandbox"

    async def provision(self) -> None:
        return None

    async def _bind_runtime(self, sandbox_id: str) -> None:
        return None


class ToyWorker(Worker):
    type_slug: ClassVar[str] = "toy-worker"

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        yield WorkerOutput(output=f"completed {task.task_slug}", success=True)


class _SessionContext:
    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *args: object) -> None:
        if args[0] is not None:
            self._session.rollback()
        return None


class _ResourceService:
    pass


class _DashboardEmitter:
    async def graph_mutation(self, row: object) -> None:
        return None


async def _dispatch_task_ready(run_id: UUID, definition_id: UUID, task_id: UUID) -> None:
    return None


class ToyWorkflowHarness(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    run_id: UUID
    parent_task_id: UUID
    parent_task: Task
    context: WorkerContext
    session: Session

    def child_task(self, *, task_slug: str, description: str) -> Task:
        return self.parent_task.model_copy(
            update={
                "task_slug": task_slug,
                "description": description,
                "parent_task_slug": self.parent_task.task_slug,
                "dependency_task_slugs": (),
            },
            deep=True,
        )

    def nodes(self) -> list[RunGraphNode]:
        return list(
            self.session.exec(
                select(RunGraphNode)
                .where(RunGraphNode.run_id == self.run_id)
                .order_by(RunGraphNode.task_slug)
            ).all()
        )

    def edges(self) -> list[RunGraphEdge]:
        return list(
            self.session.exec(select(RunGraphEdge).where(RunGraphEdge.run_id == self.run_id)).all()
        )

    def definition_tasks(self) -> list[ExperimentDefinitionTask]:
        return list(self.session.exec(select(ExperimentDefinitionTask)).all())


def make_toy_workflow_harness(monkeypatch: pytest.MonkeyPatch) -> ToyWorkflowHarness:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    monkeypatch.setattr(
        management_module,
        "get_session",
        lambda: _SessionContext(session),
    )

    run_id = uuid4()
    definition_id = uuid4()
    parent_task = Task(
        task_slug="parent",
        instance_key="sample-1",
        description="Parent task",
        worker=ToyWorker(name="toy", model="test:none"),
        sandbox=ToySandbox(),
        evaluators=(),
    )
    session.add(
        RunRecord(
            id=run_id,
            definition_id=definition_id,
            benchmark_type="toy",
            instance_key="sample-1",
            worker_team_json={},
            status=RunStatus.EXECUTING,
        )
    )
    parent = RunGraphNode(
        run_id=run_id,
        instance_key="sample-1",
        task_slug=parent_task.task_slug,
        description=parent_task.description,
        status="running",
        assigned_worker_slug=parent_task.worker.type_slug,
        task_json=parent_task.model_dump(mode="json"),
        is_dynamic=False,
        parent_task_id=None,
        level=0,
    )
    dependency = RunGraphNode(
        run_id=run_id,
        instance_key="sample-1",
        task_slug="dependency",
        description="Dependency task",
        status="completed",
        assigned_worker_slug=parent_task.worker.type_slug,
        task_json=parent_task.model_copy(
            update={"task_slug": "dependency", "description": "Dependency task"},
            deep=True,
        ).model_dump(mode="json"),
        is_dynamic=False,
        parent_task_id=None,
        level=0,
    )
    session.add(parent)
    session.add(dependency)
    session.commit()

    context = WorkerContext(
        run_id=run_id,
        task_id=parent.task_id,
        execution_id=uuid4(),
        definition_id=definition_id,
        sandbox_id="toy-sandbox-id",
        task_mgmt=TaskManagementService(
            dashboard_emitter=_DashboardEmitter(),
            task_ready_dispatcher=_dispatch_task_ready,
        ),
        task_inspect=TaskInspectionService(),
        resource_service=_ResourceService(),
        session_factory=lambda: _SessionContext(session),
    )
    return ToyWorkflowHarness(
        run_id=run_id,
        parent_task_id=parent.task_id,
        parent_task=parent_task,
        context=context,
        session=session,
    )


@pytest.fixture
def toy_workflow_harness(monkeypatch: pytest.MonkeyPatch) -> ToyWorkflowHarness:
    return make_toy_workflow_harness(monkeypatch)
