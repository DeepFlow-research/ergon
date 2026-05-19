from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from ergon_core.api.benchmark.task import EmptyTaskPayload, Task
from ergon_core.api.errors import ContainmentViolation
from ergon_core.api.worker.context import WorkerContext
from ergon_core.api.worker.results import AwaitCompletionNotSupportedError, SpawnedTaskHandle
from ergon_core.core.application.resources.models import RunResourceView
from ergon_core.core.application.resources.repository import RunResourceRepository
from ergon_core.core.application.tasks.models import (
    CancelTaskCommand,
    RefineTaskCommand,
    RestartTaskCommand,
    SubtaskInfo,
)
from ergon_core.core.persistence.shared.enums import RunResourceKind
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunTaskExecution,
)
from ergon_core.core.shared.utils import utcnow
from ergon_core.test_support import task_factory


class _FacadeTask(Task[EmptyTaskPayload]):
    pass


class _Session:
    pass


@contextmanager
def _session_factory():
    yield _Session()


def _sql_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


class _FakeTaskManagement:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, object]] = []

    async def spawn_dynamic_task(self, *, run_id, parent_task_id, task, depends_on):
        self.calls.append(("spawn", run_id, parent_task_id, task, depends_on))
        return SpawnedTaskHandle(task_id=uuid4())

    async def cancel_task(self, session, command: CancelTaskCommand):
        self.calls.append(("cancel", session, command))

    async def refine_task(self, session, command: RefineTaskCommand):
        self.calls.append(("refine", session, command))

    async def restart_task(self, session, command: RestartTaskCommand):
        self.calls.append(("restart", session, command))
        return SimpleNamespace(task_id=command.task_id)


class _FakeInspection:
    def __init__(self, descendants: frozenset | None = None) -> None:
        self.descendant_set = descendants or frozenset()
        self.calls: list[tuple[str, object]] = []

    def list_subtasks(self, session, *, run_id, parent_task_id):
        self.calls.append(("list_subtasks", session, run_id, parent_task_id))
        return [
            SubtaskInfo(
                task_id=uuid4(),
                task_slug="child",
                description="child",
                status="pending",
                depends_on=[],
                output=None,
                error=None,
            )
        ]

    def get_subtask(self, session, *, run_id, node_id):
        self.calls.append(("get_subtask", session, run_id, node_id))
        return SubtaskInfo(
            task_id=node_id,
            task_slug="target",
            description="target",
            status="pending",
            depends_on=[],
            output=None,
            error=None,
        )

    async def descendant_ids(self, *, run_id, root_task_id):
        self.calls.append(("descendant_ids", run_id, root_task_id))
        return self.descendant_set


class _FakeResources:
    def __init__(self, *, run_id, other_run_id, blob_path: Path) -> None:
        self.run_id = run_id
        self.other_run_id = other_run_id
        self.blob_path = blob_path
        self.calls: list[tuple[str, object]] = []

    def list_for_run(self, session, **kwargs):
        self.calls.append(("list_for_run", session, kwargs))
        return [
            RunResourceView(
                id=uuid4(),
                run_id=self.run_id,
                task_execution_id=kwargs.get("task_execution_id"),
                kind=RunResourceKind.REPORT,
                name="report.txt",
                mime_type="text/plain",
                file_path=str(self.blob_path),
                size_bytes=2,
                content_hash=None,
                error=None,
                metadata={},
                created_at=utcnow(),
            )
        ]

    def get(self, session, resource_id):
        self.calls.append(("get", session, resource_id))
        run_id = self.other_run_id if str(resource_id).endswith("ffff") else self.run_id
        return SimpleNamespace(run_id=run_id, file_path=str(self.blob_path))


def _context(*, run_id, task_id, inspect=None, resource_repo=None) -> WorkerContext:
    return WorkerContext._for_job(
        run_id=run_id,
        task_id=task_id,
        execution_id=uuid4(),
        definition_id=uuid4(),
        sandbox_id="sbx",
        task_mgmt=_FakeTaskManagement(),
        task_inspect=inspect or _FakeInspection(),
        resource_repo=resource_repo or SimpleNamespace(),
        session_factory=_session_factory,
    )


@pytest.mark.asyncio
async def test_facade_mutations_call_current_service_command_signatures() -> None:
    run_id = uuid4()
    root_id = uuid4()
    child_id = uuid4()
    inspect = _FakeInspection(frozenset({child_id}))
    mgmt = _FakeTaskManagement()
    context = WorkerContext._for_job(
        run_id=run_id,
        task_id=root_id,
        execution_id=uuid4(),
        definition_id=uuid4(),
        sandbox_id="sbx",
        task_mgmt=mgmt,
        task_inspect=inspect,
        resource_repo=SimpleNamespace(),
        session_factory=_session_factory,
    )

    await context.cancel_task(child_id, reason="advisory only")
    await context.refine_task(child_id, description="new description")
    restarted = await context.restart_task(child_id)

    assert isinstance(mgmt.calls[0][2], CancelTaskCommand)
    assert mgmt.calls[0][2].task_id == child_id
    assert isinstance(mgmt.calls[1][2], RefineTaskCommand)
    assert mgmt.calls[1][2].new_description == "new description"
    assert isinstance(mgmt.calls[2][2], RestartTaskCommand)
    assert restarted.task_id == child_id


@pytest.mark.asyncio
async def test_spawn_task_uses_empty_tuple_dependency_default() -> None:
    run_id = uuid4()
    root_id = uuid4()
    mgmt = _FakeTaskManagement()
    context = WorkerContext._for_job(
        run_id=run_id,
        task_id=root_id,
        execution_id=uuid4(),
        definition_id=uuid4(),
        sandbox_id="sbx",
        task_mgmt=mgmt,
        task_inspect=_FakeInspection(),
        resource_repo=SimpleNamespace(),
        session_factory=_session_factory,
    )

    await context.spawn_task(
        _FacadeTask(
            task_slug="child",
            instance_key="sample-1",
            description="spawned child",
            worker=task_factory.TestWorker(name="worker", model="test:none"),
            sandbox=task_factory.TestSandbox(),
        )
    )

    assert mgmt.calls[0][4] == ()


@pytest.mark.asyncio
async def test_facade_inspection_uses_current_service_names() -> None:
    run_id = uuid4()
    root_id = uuid4()
    child_id = uuid4()
    inspect = _FakeInspection(frozenset({child_id}))
    context = _context(run_id=run_id, task_id=root_id, inspect=inspect)

    subtasks = await context.subtasks()
    descendants = await context.descendants()
    task = await context.get_task(child_id)

    assert len(subtasks) == 1
    assert len(descendants) == 1
    assert task.task_id == child_id
    assert [call[0] for call in inspect.calls] == [
        "list_subtasks",
        "descendant_ids",
        "get_subtask",
        "descendant_ids",
        "get_subtask",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["cancel_task", "refine_task", "restart_task", "get_task"])
async def test_lifecycle_methods_enforce_descendant_containment(method: str) -> None:
    run_id = uuid4()
    root_id = uuid4()
    outside_id = uuid4()
    context = _context(run_id=run_id, task_id=root_id, inspect=_FakeInspection(frozenset()))

    with pytest.raises(ContainmentViolation):
        if method == "refine_task":
            await context.refine_task(outside_id, description="new")
        else:
            await getattr(context, method)(outside_id)


@pytest.mark.asyncio
async def test_resources_are_run_scoped_not_descendant_scoped(tmp_path: Path) -> None:
    run_id = uuid4()
    other_run_id = uuid4()
    root_id = uuid4()
    sibling_task_id = uuid4()
    execution_id = uuid4()
    blob = tmp_path / "blob.txt"
    blob.write_bytes(b"ok")
    repo = _FakeResources(run_id=run_id, other_run_id=other_run_id, blob_path=blob)
    context = _context(run_id=run_id, task_id=root_id, resource_repo=repo)

    resources = await context.resources(task_id=sibling_task_id, execution_id=execution_id)
    data = await context.read_resource(resources[0].id)

    assert data == b"ok"
    assert repo.calls[0][2]["task_id"] == sibling_task_id
    assert repo.calls[0][2]["task_execution_id"] == execution_id


@pytest.mark.asyncio
async def test_read_resource_rejects_cross_run_rows(tmp_path: Path) -> None:
    run_id = uuid4()
    other_run_id = uuid4()
    blob = tmp_path / "blob.txt"
    blob.write_bytes(b"ok")
    repo = _FakeResources(run_id=run_id, other_run_id=other_run_id, blob_path=blob)
    context = _context(run_id=run_id, task_id=uuid4(), resource_repo=repo)
    cross_run_resource_id = uuid4()
    cross_run_resource_id = type(cross_run_resource_id)(f"{str(cross_run_resource_id)[:-4]}ffff")

    with pytest.raises(ContainmentViolation):
        await context.read_resource(cross_run_resource_id)


@pytest.mark.asyncio
async def test_resources_use_repository_run_scope_with_real_rows(tmp_path: Path) -> None:
    session = _sql_session()
    run_id = uuid4()
    other_run_id = uuid4()
    definition_id = uuid4()
    root_id = uuid4()
    sibling_id = uuid4()
    sibling_execution_id = uuid4()
    other_execution_id = uuid4()
    blob = tmp_path / "report.txt"
    blob.write_bytes(b"report")
    session.add_all(
        [
            ExperimentDefinition(
                id=definition_id,
                benchmark_type="bench",
                name="bench",
                metadata_json={},
            ),
            RunRecord(
                id=run_id,
                definition_id=definition_id,
                benchmark_type="bench",
                instance_key="sample-1",
                worker_team_json={},
                status=RunStatus.EXECUTING,
            ),
            RunRecord(
                id=other_run_id,
                definition_id=definition_id,
                benchmark_type="bench",
                instance_key="sample-2",
                worker_team_json={},
                status=RunStatus.EXECUTING,
            ),
            RunGraphNode(
                task_id=root_id,
                run_id=run_id,
                instance_key="sample-1",
                task_slug="root",
                description="root",
                status="running",
            ),
            RunGraphNode(
                task_id=sibling_id,
                run_id=run_id,
                instance_key="sample-1",
                task_slug="sibling",
                description="sibling",
                status="completed",
            ),
            RunTaskExecution(
                id=sibling_execution_id,
                run_id=run_id,
                task_id=sibling_id,
                status=TaskExecutionStatus.COMPLETED,
            ),
            RunTaskExecution(
                id=other_execution_id,
                run_id=other_run_id,
                task_id=uuid4(),
                status=TaskExecutionStatus.COMPLETED,
            ),
            RunResource(
                run_id=run_id,
                task_execution_id=sibling_execution_id,
                kind=RunResourceKind.REPORT.value,
                name="report.txt",
                mime_type="text/plain",
                file_path=str(blob),
                size_bytes=6,
            ),
        ]
    )
    session.commit()

    @contextmanager
    def session_factory():
        yield session

    context = WorkerContext._for_job(
        run_id=run_id,
        task_id=root_id,
        execution_id=uuid4(),
        definition_id=definition_id,
        sandbox_id="sbx",
        task_mgmt=_FakeTaskManagement(),
        task_inspect=_FakeInspection(),
        resource_repo=RunResourceRepository(),
        session_factory=session_factory,
    )

    sibling_resources = await context.resources(task_id=sibling_id)
    execution_resources = await context.resources(execution_id=sibling_execution_id)
    content = await context.read_resource(sibling_resources[0].id)

    assert [r.name for r in sibling_resources] == ["report.txt"]
    assert [r.name for r in execution_resources] == ["report.txt"]
    assert content == b"report"
    with pytest.raises(ContainmentViolation):
        await context.resources(execution_id=other_execution_id)


def test_context_requires_facade_services_at_construction() -> None:
    with pytest.raises(ValidationError, match="task_mgmt"):
        WorkerContext(run_id=uuid4(), task_id=uuid4(), execution_id=uuid4(), sandbox_id="sbx")

    with pytest.raises(ValidationError, match="injected dependencies"):
        WorkerContext(
            run_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
            sandbox_id="sbx",
            task_mgmt=None,
            task_inspect=_FakeInspection(),
            resource_repo=SimpleNamespace(),
            session_factory=_session_factory,
        )


@pytest.mark.asyncio
async def test_spawned_task_handle_wait_has_public_deferred_error() -> None:
    with pytest.raises(AwaitCompletionNotSupportedError, match="deferred in v2"):
        await SpawnedTaskHandle(task_id=uuid4()).wait()
