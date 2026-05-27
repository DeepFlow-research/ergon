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
    attempt_number: int,
    started_at: datetime,
    message: str = "output",
) -> SampleTaskAttempt:
    return SampleTaskAttempt(
        sample_id=sample_id,
        task_id=task_id,
        attempt_number=attempt_number,
        status=TaskExecutionStatus.COMPLETED,
        started_at=started_at,
        final_assistant_message=message,
    )


def test_latest_for_node_orders_by_attempt_then_started_at() -> None:
    session = _session()
    sample_id = _run(session)
    node_id = _node(session, sample_id)
    now = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    older_attempt_two = _execution(
        sample_id=sample_id,
        task_id=node_id,
        attempt_number=2,
        started_at=now,
        message="attempt-two-old",
    )
    newer_attempt_one = _execution(
        sample_id=sample_id,
        task_id=node_id,
        attempt_number=1,
        started_at=now + timedelta(minutes=10),
        message="attempt-one-newer",
    )
    newer_attempt_two = _execution(
        sample_id=sample_id,
        task_id=node_id,
        attempt_number=2,
        started_at=now + timedelta(minutes=5),
        message="attempt-two-new",
    )
    session.add_all([older_attempt_two, newer_attempt_one, newer_attempt_two])
    session.commit()

    latest = TaskExecutionRepository().latest_for_node(session, node_id)

    assert latest is not None
    assert latest.id == newer_attempt_two.id
    assert latest.id != newer_attempt_one.id


def test_next_attempt_counts_existing_node_executions() -> None:
    session = _session()
    sample_id = _run(session)
    node_id = _node(session, sample_id)
    now = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    session.add_all(
        [
            _execution(sample_id=sample_id, task_id=node_id, attempt_number=1, started_at=now),
            _execution(sample_id=sample_id, task_id=node_id, attempt_number=2, started_at=now),
        ]
    )
    session.commit()

    assert TaskExecutionRepository().next_attempt_for_node(session, sample_id, node_id) == 3
