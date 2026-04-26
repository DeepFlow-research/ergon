from pathlib import Path
from uuid import UUID, uuid4

import pytest
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphNode
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunResourceKind,
    RunTaskExecution,
)
from ergon_core.core.runtime.services.workflow_service import WorkflowService
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
    status: str = "completed",
    parent_node_id: UUID | None = None,
    level: int = 0,
) -> RunGraphNode:
    return RunGraphNode(
        run_id=run_id,
        instance_key="instance",
        task_slug=slug,
        description=f"Task {slug}",
        status=status,
        assigned_worker_slug="worker",
        parent_node_id=parent_node_id,
        level=level,
    )


def _execution(
    *,
    run_id: UUID,
    node_id: UUID,
    status: TaskExecutionStatus = TaskExecutionStatus.COMPLETED,
) -> RunTaskExecution:
    return RunTaskExecution(
        run_id=run_id,
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
    session.add(
        RunRecord(
            id=run_id,
            experiment_definition_id=uuid4(),
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
                source_node_id=a.id,
                target_node_id=b.id,
                status="satisfied",
            ),
            RunGraphEdge(
                run_id=run_id,
                source_node_id=b.id,
                target_node_id=c.id,
                status="satisfied",
            ),
        ]
    )
    exec_a = _execution(run_id=run_id, node_id=a.id)
    exec_b = _execution(run_id=run_id, node_id=b.id)
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
        node_id=c.id,
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
    peer_exec = _execution(run_id=run_id, node_id=peer.id)
    other_exec = _execution(run_id=other_run_id, node_id=other.id)
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
        node_id=current.id,
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
    producer_exec = _execution(run_id=run_id, node_id=producer.id)
    consumer_exec = _execution(
        run_id=run_id, node_id=consumer.id, status=TaskExecutionStatus.RUNNING
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
        current_node_id=consumer.id,
        current_execution_id=consumer_exec.id,
        sandbox_task_key=consumer.id,
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
        (consumer.id, source.file_path, "/workspace/imported/producer/paper (copy).pdf")
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
    producer_exec = _execution(run_id=run_id, node_id=producer.id)
    consumer_exec = _execution(
        run_id=run_id, node_id=consumer.id, status=TaskExecutionStatus.RUNNING
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
        current_node_id=consumer.id,
        current_execution_id=consumer_exec.id,
        sandbox_task_key=consumer.id,
        benchmark_type="test",
        resource_id=source.id,
        destination="selected/paper.pdf",
        dry_run=True,
    )

    assert result.sandbox_path == "/workspace/selected/paper (copy).pdf"
    assert result.copied_resource_id is None
