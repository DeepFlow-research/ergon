from pathlib import Path
from uuid import UUID, uuid4

import pytest
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphNode
from ergon_core.core.persistence.shared.enums import (
    RunResourceKind,
    RunStatus,
    TaskExecutionStatus,
)
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunTaskExecution,
)
from ergon_core.core.application.workflows.service import WorkflowService
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


def _session() -> Session:
    _ = ExperimentDefinition
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _node(
    *,
    run_id: UUID,
    slug: str,
    description: str | None = None,
    status: str = "completed",
    parent_task_id: UUID | None = None,
    level: int = 0,
) -> RunGraphNode:
    return RunGraphNode(
        run_id=run_id,
        instance_key="instance",
        task_slug=slug,
        description=description or f"Task {slug}",
        status=status,
        assigned_worker_slug="worker",
        parent_task_id=parent_task_id,
        level=level,
    )


def _edge(*, run_id: UUID, source_task_id: UUID, target_task_id: UUID) -> RunGraphEdge:
    return RunGraphEdge(
        run_id=run_id,
        source_task_id=source_task_id,
        target_task_id=target_task_id,
        status="satisfied",
    )


def _execution(
    *,
    run_id: UUID,
    node_id: UUID,
    status: TaskExecutionStatus = TaskExecutionStatus.COMPLETED,
) -> RunTaskExecution:
    return RunTaskExecution(
        run_id=run_id,
        task_id=node_id,
        node_id=node_id,
        status=status,
        final_assistant_message=f"output for {node_id}",
    )


def _resource(
    *,
    run_id: UUID,
    execution_id: UUID,
    name: str,
    path: Path,
    content: bytes,
    kind: RunResourceKind = RunResourceKind.REPORT,
) -> RunResource:
    path.write_bytes(content)
    return RunResource(
        run_id=run_id,
        task_execution_id=execution_id,
        kind=kind.value,
        name=name,
        mime_type="text/plain",
        file_path=str(path),
        size_bytes=len(content),
        content_hash=f"hash-{name}",
    )


def _run(session: Session) -> UUID:
    run_id = uuid4()
    definition_id = uuid4()
    session.add(
        RunRecord(
            id=run_id,
            definition_id=uuid4(),
            definition_id=definition_id,
            benchmark_type="ci-workflow-service",
            instance_key="sample-1",
            worker_team_json={"primary": "test-worker"},
            status=RunStatus.EXECUTING,
        )
    )
    return run_id


def test_input_scope_uses_immediate_upstream_resources_only(tmp_path: Path) -> None:
    session = _session()
    run_id = _run(session)
    a = _node(run_id=run_id, slug="a")
    b = _node(run_id=run_id, slug="b")
    c = _node(run_id=run_id, slug="c")
    session.add_all([a, b, c])
    session.flush()
    session.add_all(
        [
            RunGraphEdge(
                run_id=run_id,
                source_task_id=a.task_id,
                target_task_id=b.task_id,
                status="satisfied",
            ),
            RunGraphEdge(
                run_id=run_id,
                source_task_id=b.task_id,
                target_task_id=c.task_id,
                status="satisfied",
            ),
        ]
    )
    exec_a = _execution(run_id=run_id, node_id=a.task_id)
    exec_b = _execution(run_id=run_id, node_id=b.task_id)
    session.add_all([exec_a, exec_b])
    session.flush()
    session.add_all(
        [
            _resource(
                run_id=run_id,
                execution_id=exec_a.id,
                name="a.txt",
                path=tmp_path / "a.txt",
                content=b"a",
            ),
            _resource(
                run_id=run_id,
                execution_id=exec_b.id,
                name="b.txt",
                path=tmp_path / "b.txt",
                content=b"b",
            ),
        ]
    )
    session.commit()

    resources = WorkflowService().list_resources(
        session,
        run_id=run_id,
        node_id=c.task_id,
        scope="input",
    )

    assert [resource.name for resource in resources] == ["b.txt"]


def test_visible_scope_stays_inside_current_run(tmp_path: Path) -> None:
    session = _session()
    run_id = _run(session)
    other_run_id = _run(session)
    current = _node(run_id=run_id, slug="current")
    peer = _node(run_id=run_id, slug="peer")
    other = _node(run_id=other_run_id, slug="other")
    session.add_all([current, peer, other])
    session.flush()
    peer_exec = _execution(run_id=run_id, node_id=peer.task_id)
    other_exec = _execution(run_id=other_run_id, node_id=other.task_id)
    session.add_all([peer_exec, other_exec])
    session.flush()
    session.add_all(
        [
            _resource(
                run_id=run_id,
                execution_id=peer_exec.id,
                name="peer.txt",
                path=tmp_path / "peer.txt",
                content=b"peer",
            ),
            _resource(
                run_id=other_run_id,
                execution_id=other_exec.id,
                name="other.txt",
                path=tmp_path / "other.txt",
                content=b"other",
            ),
        ]
    )
    session.commit()

    resources = WorkflowService().list_resources(
        session,
        run_id=run_id,
        node_id=current.task_id,
        scope="visible",
    )

    assert [resource.name for resource in resources] == ["peer.txt"]


@pytest.mark.asyncio
async def test_materialize_resource_creates_current_task_owned_copy(tmp_path: Path) -> None:
    session = _session()
    run_id = _run(session)
    producer = _node(run_id=run_id, slug="producer")
    consumer = _node(run_id=run_id, slug="consumer")
    session.add_all([producer, consumer])
    session.flush()
    producer_exec = _execution(run_id=run_id, node_id=producer.task_id)
    consumer_exec = _execution(
        run_id=run_id, node_id=consumer.task_id, status=TaskExecutionStatus.RUNNING
    )
    session.add_all([producer_exec, consumer_exec])
    session.flush()
    source = _resource(
        run_id=run_id,
        execution_id=producer_exec.id,
        name="paper.pdf",
        path=tmp_path / "paper.pdf",
        content=b"paper",
        kind=RunResourceKind.REPORT,
    )
    session.add(source)
    session.commit()

    class Manager:
        uploads: list[tuple[UUID, str, str]] = []

        async def upload_file(self, task_id: UUID, local_path: str, sandbox_path: str) -> None:
            self.uploads.append((task_id, local_path, sandbox_path))

    manager = Manager()
    result = await WorkflowService(
        sandbox_manager_factory=lambda _benchmark_type: manager
    ).materialize_resource(
        session,
        run_id=run_id,
        current_node_id=consumer.task_id,
        current_execution_id=consumer_exec.id,
        sandbox_task_key=consumer.task_id,
        benchmark_type="test",
        resource_id=source.id,
        destination=None,
        dry_run=False,
    )

    copy = session.exec(
        select(RunResource).where(RunResource.id == result.copied_resource_id)
    ).one()
    original = session.get(RunResource, source.id)

    assert copy.id != source.id
    assert copy.task_execution_id == consumer_exec.id
    assert copy.kind == RunResourceKind.IMPORT.value
    assert copy.name == "paper (copy).pdf"
    assert copy.file_path == source.file_path
    assert copy.content_hash == source.content_hash
    assert copy.copied_from_resource_id == source.id
    assert original is not None
    assert original.task_execution_id == producer_exec.id
    assert manager.uploads == [
        (consumer.task_id, source.file_path, "/workspace/imported/producer/paper (copy).pdf")
    ]


@pytest.mark.asyncio
async def test_materialize_resource_dry_run_keeps_copy_name_for_explicit_destination(
    tmp_path: Path,
) -> None:
    session = _session()
    run_id = _run(session)
    producer = _node(run_id=run_id, slug="producer")
    consumer = _node(run_id=run_id, slug="consumer")
    session.add_all([producer, consumer])
    session.flush()
    producer_exec = _execution(run_id=run_id, node_id=producer.task_id)
    consumer_exec = _execution(
        run_id=run_id, node_id=consumer.task_id, status=TaskExecutionStatus.RUNNING
    )
    session.add_all([producer_exec, consumer_exec])
    session.flush()
    source = _resource(
        run_id=run_id,
        execution_id=producer_exec.id,
        name="paper.pdf",
        path=tmp_path / "paper.pdf",
        content=b"paper",
    )
    session.add(source)
    session.commit()

    result = await WorkflowService().materialize_resource(
        session,
        run_id=run_id,
        current_node_id=consumer.task_id,
        current_execution_id=consumer_exec.id,
        sandbox_task_key=consumer.task_id,
        benchmark_type="test",
        resource_id=source.id,
        destination="selected/paper.pdf",
        dry_run=True,
    )

    assert result.sandbox_path == "/workspace/selected/paper (copy).pdf"
    assert result.copied_resource_id is None


def test_resource_location_describes_producer_and_workspace_destination(tmp_path: Path) -> None:
    session = _session()
    run_id = _run(session)
    producer = _node(run_id=run_id, slug="producer")
    session.add(producer)
    session.flush()
    producer_exec = _execution(run_id=run_id, node_id=producer.task_id)
    session.add(producer_exec)
    session.flush()
    source = _resource(
        run_id=run_id,
        execution_id=producer_exec.id,
        name="paper.pdf",
        path=tmp_path / "paper.pdf",
        content=b"paper",
    )
    session.add(source)
    session.commit()

    location = WorkflowService().get_resource_location(
        session,
        run_id=run_id,
        resource_id=source.id,
    )

    assert location.resource.resource_id == source.id
    assert location.producer_task_slug == "producer"
    assert location.default_sandbox_path == "/workspace/imported/producer/paper (copy).pdf"
    assert location.local_file_path == source.file_path


def test_task_workspace_reports_latest_execution_and_resources(tmp_path: Path) -> None:
    session = _session()
    run_id = _run(session)
    current = _node(run_id=run_id, slug="current", status="running")
    upstream = _node(run_id=run_id, slug="upstream")
    session.add_all([current, upstream])
    session.flush()
    current_exec = _execution(
        run_id=run_id,
        node_id=current.task_id,
        status=TaskExecutionStatus.RUNNING,
    )
    upstream_exec = _execution(run_id=run_id, node_id=upstream.task_id)
    session.add_all([current_exec, upstream_exec])
    session.flush()
    session.add(
        _edge(run_id=run_id, source_task_id=upstream.task_id, target_task_id=current.task_id)
    )
    session.add_all(
        [
            _resource(
                run_id=run_id,
                execution_id=current_exec.id,
                name="own.txt",
                path=tmp_path / "own.txt",
                content=b"own",
            ),
            _resource(
                run_id=run_id,
                execution_id=upstream_exec.id,
                name="input.txt",
                path=tmp_path / "input.txt",
                content=b"input",
            ),
        ]
    )
    session.commit()

    workspace = WorkflowService().get_task_workspace(
        session,
        run_id=run_id,
        node_id=current.task_id,
    )

    assert workspace.task.task_slug == "current"
    assert workspace.latest_execution is not None
    assert workspace.latest_execution.execution_id == current_exec.id
    assert [resource.name for resource in workspace.own_resources] == ["own.txt"]
    assert [resource.name for resource in workspace.input_resources] == ["input.txt"]


@pytest.mark.asyncio
async def test_materialize_resource_rejects_parent_directory_destination(
    tmp_path: Path,
) -> None:
    session = _session()
    run_id = _run(session)
    producer = _node(run_id=run_id, slug="producer")
    consumer = _node(run_id=run_id, slug="consumer")
    session.add_all([producer, consumer])
    session.flush()
    producer_exec = _execution(run_id=run_id, node_id=producer.task_id)
    consumer_exec = _execution(
        run_id=run_id,
        node_id=consumer.task_id,
        status=TaskExecutionStatus.RUNNING,
    )
    session.add_all([producer_exec, consumer_exec])
    session.flush()
    source = _resource(
        run_id=run_id,
        execution_id=producer_exec.id,
        name="paper.pdf",
        path=tmp_path / "paper.pdf",
        content=b"paper",
    )
    session.add(source)
    session.commit()

    with pytest.raises(ValueError, match="destination must stay inside /workspace"):
        await WorkflowService().materialize_resource(
            session,
            run_id=run_id,
            current_node_id=consumer.task_id,
            current_execution_id=consumer_exec.id,
            sandbox_task_key=consumer.task_id,
            benchmark_type="test",
            resource_id=source.id,
            destination="../escape/paper.pdf",
            dry_run=True,
        )


@pytest.mark.asyncio
async def test_add_task_dry_run_does_not_write_node() -> None:
    session = _session()
    run_id = _run(session)
    parent = _node(run_id=run_id, slug="parent", level=1)
    session.add(parent)
    session.commit()

    result = await WorkflowService().add_task(
        session,
        run_id=run_id,
        parent_task_id=parent.task_id,
        task_slug="child",
        description="Child task",
        assigned_worker_slug="minif2f-react",
        dry_run=True,
    )

    nodes = session.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).all()
    assert len(nodes) == 1
    assert result.action == "add-task"
    assert result.dry_run is True
    assert result.node is not None
    assert result.node.task_slug == "child"
    assert result.node.parent_task_id == parent.task_id
    assert result.node.level == 2


@pytest.mark.asyncio
async def test_add_task_non_dry_run_requires_object_bound_task() -> None:
    session = _session()
    run_id = _run(session)
    parent = _node(run_id=run_id, slug="parent", level=1)
    session.add(parent)
    session.commit()
    dispatched = []

    async def dispatch_task_ready(run_id, definition_id, node_id):
        dispatched.append((run_id, definition_id, node_id))

    with pytest.raises(ValueError, match="requires an object-bound Task"):
        await WorkflowService(task_ready_dispatcher=dispatch_task_ready).add_task(
            session,
            run_id=run_id,
            parent_task_id=parent.task_id,
            task_slug="child",
            description="Child task",
            assigned_worker_slug="minif2f-react",
            dry_run=False,
        )

    inserted = session.exec(
        select(RunGraphNode).where(
            RunGraphNode.run_id == run_id,
            RunGraphNode.task_slug == "child",
        )
    ).first()
    assert inserted is None
    assert dispatched == []


@pytest.mark.asyncio
async def test_add_task_rejects_unknown_worker_slug_before_creating_node() -> None:
    session = _session()
    run_id = _run(session)
    parent = _node(run_id=run_id, slug="parent", status="running")
    session.add(parent)
    session.commit()

    async def dispatch_task_ready(run_id: UUID, definition_id: UUID, node_id: UUID) -> None:
        raise AssertionError("invalid worker should not dispatch")

    with pytest.raises(ValueError, match="requires an object-bound Task"):
        await WorkflowService(task_ready_dispatcher=dispatch_task_ready).add_task(
            session,
            run_id=run_id,
            parent_task_id=parent.task_id,
            task_slug="bad-worker",
            description="Should not be inserted",
            assigned_worker_slug="not-a-real-worker",
            dry_run=False,
        )

    inserted = session.exec(
        select(RunGraphNode).where(
            RunGraphNode.run_id == run_id,
            RunGraphNode.task_slug == "bad-worker",
        )
    ).first()
    assert inserted is None


@pytest.mark.asyncio
async def test_add_edge_writes_dependency_between_slugs() -> None:
    session = _session()
    run_id = _run(session)
    source = _node(run_id=run_id, slug="source")
    target = _node(run_id=run_id, slug="target")
    session.add_all([source, target])
    session.commit()

    result = await WorkflowService().add_edge(
        session,
        run_id=run_id,
        source_task_slug="source",
        target_task_slug="target",
        dry_run=False,
    )

    assert result.action == "add-edge"
    assert result.edge is not None
    edge = session.get(RunGraphEdge, result.edge.edge_id)
    assert edge is not None
    assert edge.source_task_id == source.task_id
    assert edge.target_task_id == target.task_id
    assert edge.status == "pending"


@pytest.mark.asyncio
async def test_update_task_description_changes_only_description() -> None:
    session = _session()
    run_id = _run(session)
    node = _node(run_id=run_id, slug="target", description="Old")
    session.add(node)
    session.commit()

    result = await WorkflowService().update_task_description(
        session,
        run_id=run_id,
        task_slug="target",
        description="New description",
        dry_run=False,
    )

    refreshed = session.get(RunGraphNode, (run_id, node.task_id))
    assert refreshed is not None
    assert refreshed.description == "New description"
    assert refreshed.task_slug == "target"
    assert result.node is not None
    assert result.node.description == "New description"
