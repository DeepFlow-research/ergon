from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.shared.enums import SampleStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord, SampleTaskAttempt
from ergon_core.core.application.runtime.task_execution_repository import TaskExecutionRepository
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _run(session: Session) -> UUID:
    sample_id = uuid4()
    session.add(
        SampleRecord(
            id=sample_id,
            benchmark_type="ci-task-execution-repository",
            instance_key="sample-1",
            worker_team_json={"primary": "test-worker"},
            status=SampleStatus.EXECUTING,
        )
    )
    return sample_id


def _node(session: Session, sample_id: UUID) -> UUID:
    node = SampleGraphNode(
        sample_id=sample_id,
        instance_key="sample-1",
        task_slug="task",
        description="Task",
        status="running",
    )
    session.add(node)
    session.flush()
    return node.task_id


def _execution(
    *,
    sample_id: UUID,
    task_id: UUID,
    started_at: datetime,
    created_at: datetime | None = None,
    message: str = "output",
) -> SampleTaskAttempt:
    return SampleTaskAttempt(
        sample_id=sample_id,
        task_id=task_id,
        status=TaskExecutionStatus.COMPLETED,
        started_at=started_at,
        created_at=created_at or started_at,
        final_assistant_message=message,
    )


def test_latest_for_node_orders_by_created_at_then_id() -> None:
    session = _session()
    sample_id = _run(session)
    node_id = _node(session, sample_id)
    now = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    older_attempt = _execution(
        sample_id=sample_id,
        task_id=node_id,
        started_at=now,
        created_at=now,
        message="attempt-old",
    )
    newest_attempt = _execution(
        sample_id=sample_id,
        task_id=node_id,
        started_at=now,
        created_at=now + timedelta(minutes=10),
        message="attempt-newest",
    )
    middle_attempt = _execution(
        sample_id=sample_id,
        task_id=node_id,
        started_at=now + timedelta(minutes=20),
        created_at=now + timedelta(minutes=5),
        message="attempt-middle",
    )
    session.add_all([older_attempt, newest_attempt, middle_attempt])
    session.commit()

    latest = TaskExecutionRepository().latest_for_node(session, node_id)

    assert latest is not None
    assert latest.id == newest_attempt.id
    assert latest.id != middle_attempt.id


def test_latest_for_node_uses_id_as_deterministic_tie_breaker() -> None:
    session = _session()
    sample_id = _run(session)
    node_id = _node(session, sample_id)
    now = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    first = _execution(sample_id=sample_id, task_id=node_id, started_at=now, created_at=now)
    second = _execution(sample_id=sample_id, task_id=node_id, started_at=now, created_at=now)
    session.add_all([first, second])
    session.commit()

    latest = TaskExecutionRepository().latest_for_node(session, node_id)

    assert latest is not None
    assert latest.id == max(first.id, second.id)
