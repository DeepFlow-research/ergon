from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import RunRecord, RunTaskExecution
from ergon_core.core.application.tasks.repository import TaskExecutionRepository
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
    run_id = uuid4()
    session.add(
        RunRecord(
            id=run_id,
            experiment_id=uuid4(),
            workflow_definition_id=uuid4(),
            benchmark_type="ci-task-execution-repository",
            instance_key="sample-1",
            worker_team_json={"primary": "test-worker"},
            status=RunStatus.EXECUTING,
        )
    )
    return run_id


def _node(session: Session, run_id: UUID) -> UUID:
    node = RunGraphNode(
        run_id=run_id,
        instance_key="sample-1",
        task_slug="task",
        description="Task",
        status="running",
    )
    session.add(node)
    session.flush()
    return node.id


def _execution(
    *,
    run_id: UUID,
    node_id: UUID,
    attempt_number: int,
    started_at: datetime,
    definition_task_id: UUID | None = None,
    message: str = "output",
) -> RunTaskExecution:
    return RunTaskExecution(
        run_id=run_id,
        node_id=node_id,
        definition_task_id=definition_task_id,
        attempt_number=attempt_number,
        status=TaskExecutionStatus.COMPLETED,
        started_at=started_at,
        final_assistant_message=message,
    )


def test_latest_for_node_orders_by_attempt_then_started_at() -> None:
    session = _session()
    run_id = _run(session)
    node_id = _node(session, run_id)
    now = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    older_attempt_two = _execution(
        run_id=run_id,
        node_id=node_id,
        attempt_number=2,
        started_at=now,
        message="attempt-two-old",
    )
    newer_attempt_one = _execution(
        run_id=run_id,
        node_id=node_id,
        attempt_number=1,
        started_at=now + timedelta(minutes=10),
        message="attempt-one-newer",
    )
    newer_attempt_two = _execution(
        run_id=run_id,
        node_id=node_id,
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
    run_id = _run(session)
    node_id = _node(session, run_id)
    now = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    session.add_all(
        [
            _execution(run_id=run_id, node_id=node_id, attempt_number=1, started_at=now),
            _execution(run_id=run_id, node_id=node_id, attempt_number=2, started_at=now),
        ]
    )
    session.commit()

    assert TaskExecutionRepository().next_attempt_for_node(session, run_id, node_id) == 3


def test_latest_for_definition_task_uses_same_ordering_as_node_lookup() -> None:
    session = _session()
    run_id = _run(session)
    node_id = _node(session, run_id)
    definition_task_id = uuid4()
    now = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    older_attempt_two = _execution(
        run_id=run_id,
        node_id=node_id,
        definition_task_id=definition_task_id,
        attempt_number=2,
        started_at=now,
        message="attempt-two-old",
    )
    newer_attempt_two = _execution(
        run_id=run_id,
        node_id=node_id,
        definition_task_id=definition_task_id,
        attempt_number=2,
        started_at=now + timedelta(minutes=5),
        message="attempt-two-new",
    )
    session.add_all([older_attempt_two, newer_attempt_two])
    session.commit()

    latest = TaskExecutionRepository().latest_for_definition_task(
        session,
        run_id,
        definition_task_id,
    )

    assert latest is not None
    assert latest.id == newer_attempt_two.id
