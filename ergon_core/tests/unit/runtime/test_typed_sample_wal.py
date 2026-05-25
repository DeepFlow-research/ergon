from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlmodel import SQLModel, Session, create_engine, select

from ergon_core.core.persistence.definitions.models import ExperimentDefinition  # noqa: F401
from ergon_core.core.persistence.samples.models import (
    SampleEdgeEventRow,
    SampleEvaluatorEventRow,
    SampleSandboxEventRow,
    SampleStatusEventRow,
    SampleTaskEventRow,
    SampleWorkerEventRow,
)
from ergon_core.core.persistence.telemetry.models import SampleRecord  # noqa: F401
from ergon_core.core.application.samples.events import SampleRuntimeEventAppender


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_typed_sample_wal_rows_have_distinct_tables_and_common_ordering_columns() -> None:
    expected_tables = {
        "sample_status_events": SampleStatusEventRow,
        "sample_task_events": SampleTaskEventRow,
        "sample_edge_events": SampleEdgeEventRow,
        "sample_worker_events": SampleWorkerEventRow,
        "sample_evaluator_events": SampleEvaluatorEventRow,
        "sample_sandbox_events": SampleSandboxEventRow,
    }

    for table_name, row_type in expected_tables.items():
        assert row_type.__tablename__ == table_name
        columns = row_type.__table__.columns
        assert "id" in columns
        assert "event_timestamp" in columns
        assert "event_type" in columns
        assert "sample_id" in columns
        assert any(
            foreign_key.column.table.name == "samples" and foreign_key.column.name == "id"
            for foreign_key in columns["sample_id"].foreign_keys
        )

    assert "payload_json" in SampleStatusEventRow.__table__.columns
    assert "task_snapshot_json" in SampleTaskEventRow.__table__.columns
    assert "edge_snapshot_json" in SampleEdgeEventRow.__table__.columns
    assert "worker_snapshot_json" in SampleWorkerEventRow.__table__.columns
    assert "evaluator_snapshot_json" in SampleEvaluatorEventRow.__table__.columns
    assert "sandbox_snapshot_json" in SampleSandboxEventRow.__table__.columns


def test_event_appender_persists_each_typed_sample_event(session: Session) -> None:
    sample_id = uuid4()
    task_id = uuid4()
    target_task_id = uuid4()
    edge_id = uuid4()
    now = datetime(2026, 5, 25, 12, 0, tzinfo=UTC)
    appender = SampleRuntimeEventAppender(session)

    appender.append_status_event(
        SampleStatusEventRow(
            sample_id=sample_id,
            event_timestamp=now,
            event_type="sample.status_changed",
            status="pending",
            payload_json={"status": "pending"},
        )
    )
    appender.append_task_event(
        SampleTaskEventRow(
            sample_id=sample_id,
            event_timestamp=now,
            event_type="task.added",
            task_id=task_id,
            task_slug="root",
            status="pending",
            task_snapshot_json={"slug": "root", "description": "Root"},
            payload_json={"task_key": "root"},
        )
    )
    appender.append_edge_event(
        SampleEdgeEventRow(
            edge_id=edge_id,
            sample_id=sample_id,
            event_timestamp=now,
            event_type="edge.added",
            source_task_id=task_id,
            target_task_id=target_task_id,
            status="pending",
            edge_snapshot_json={"status": "pending"},
            payload_json={},
        )
    )
    appender.append_worker_event(
        SampleWorkerEventRow(
            sample_id=sample_id,
            event_timestamp=now,
            event_type="worker.added",
            task_id=task_id,
            worker_slug="smoke-worker",
            worker_snapshot_json={"slug": "smoke-worker"},
            payload_json={},
        )
    )
    appender.append_evaluator_event(
        SampleEvaluatorEventRow(
            sample_id=sample_id,
            event_timestamp=now,
            event_type="evaluator.added",
            task_id=task_id,
            evaluator_slug="default",
            evaluator_snapshot_json={"slug": "default"},
            payload_json={},
        )
    )
    appender.append_sandbox_event(
        SampleSandboxEventRow(
            sample_id=sample_id,
            event_timestamp=now,
            event_type="sandbox.added",
            task_id=task_id,
            sandbox_slug="swebench",
            sandbox_snapshot_json={"slug": "swebench"},
            payload_json={},
        )
    )

    assert session.exec(select(SampleStatusEventRow)).one().status == "pending"
    assert session.exec(select(SampleTaskEventRow)).one().task_snapshot_json == {
        "slug": "root",
        "description": "Root",
    }
    assert session.exec(select(SampleEdgeEventRow)).one().edge_id == edge_id
    assert session.exec(select(SampleWorkerEventRow)).one().worker_slug == "smoke-worker"
    assert session.exec(select(SampleEvaluatorEventRow)).one().evaluator_slug == "default"
    assert session.exec(select(SampleSandboxEventRow)).one().sandbox_slug == "swebench"
