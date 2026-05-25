from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlmodel import SQLModel, Session, create_engine

from ergon_core.core.persistence.definitions.models import ExperimentDefinition  # noqa: F401
from ergon_core.core.persistence.samples.models import (
    SampleAnnotationEventRow,
    SampleEdgeEventRow,
    SampleEvaluatorEventRow,
    SampleSandboxEventRow,
    SampleStatusEventRow,
    SampleTaskEventRow,
    SampleWorkerEventRow,
)
from ergon_core.core.persistence.telemetry.models import SampleRecord  # noqa: F401
from ergon_core.core.application.samples.events import SampleRuntimeEventAppender
from ergon_core.core.application.samples.state import reconstruct_sample_runtime_state_at


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_replay_reconstructs_state_from_ordered_typed_events(session: Session) -> None:
    sample_id = uuid4()
    task_id = uuid4()
    second_task_id = uuid4()
    edge_id = UUID(int=40)
    base_time = datetime(2026, 5, 25, 12, 0, tzinfo=UTC)
    appender = SampleRuntimeEventAppender(session)

    appender.append_status_event(
        SampleStatusEventRow(
            id=UUID(int=1),
            sample_id=sample_id,
            event_timestamp=base_time,
            event_type="sample.status_changed",
            status="pending",
        )
    )
    appender.append_task_event(
        SampleTaskEventRow(
            id=UUID(int=2),
            sample_id=sample_id,
            event_timestamp=base_time,
            event_type="task.added",
            task_id=task_id,
            task_slug="root",
            status="pending",
            task_snapshot_json={"slug": "root"},
        )
    )
    appender.append_worker_event(
        SampleWorkerEventRow(
            id=UUID(int=3),
            sample_id=sample_id,
            event_timestamp=base_time,
            event_type="worker.added",
            task_id=task_id,
            worker_slug="root-worker",
            worker_snapshot_json={"slug": "root-worker"},
        )
    )
    appender.append_task_event(
        SampleTaskEventRow(
            id=UUID(int=4),
            sample_id=sample_id,
            event_timestamp=base_time + timedelta(seconds=1),
            event_type="task.added",
            task_id=second_task_id,
            task_slug="child",
            status="pending",
            task_snapshot_json={"slug": "child"},
        )
    )
    appender.append_edge_event(
        SampleEdgeEventRow(
            id=UUID(int=5),
            edge_id=edge_id,
            sample_id=sample_id,
            event_timestamp=base_time + timedelta(seconds=1),
            event_type="edge.added",
            source_task_id=task_id,
            target_task_id=second_task_id,
            status="pending",
            edge_snapshot_json={"status": "pending"},
        )
    )
    appender.append_evaluator_event(
        SampleEvaluatorEventRow(
            id=UUID(int=6),
            sample_id=sample_id,
            event_timestamp=base_time + timedelta(seconds=2),
            event_type="evaluator.added",
            task_id=task_id,
            evaluator_slug="default",
            evaluator_snapshot_json={"slug": "default"},
        )
    )
    appender.append_sandbox_event(
        SampleSandboxEventRow(
            id=UUID(int=7),
            sample_id=sample_id,
            event_timestamp=base_time + timedelta(seconds=2),
            event_type="sandbox.added",
            task_id=task_id,
            sandbox_slug="ubuntu",
            sandbox_snapshot_json={"slug": "ubuntu"},
        )
    )
    appender.append_annotation_event(
        SampleAnnotationEventRow(
            id=UUID(int=8),
            sample_id=sample_id,
            event_timestamp=base_time + timedelta(seconds=3),
            event_type="annotation.set",
            target_type="task",
            target_id=task_id,
            key="review",
            payload_json={"value": {"label": "important"}},
        )
    )
    appender.append_task_event(
        SampleTaskEventRow(
            id=UUID(int=9),
            sample_id=sample_id,
            event_timestamp=base_time + timedelta(seconds=4),
            event_type="task.status_changed",
            task_id=task_id,
            task_slug="root",
            status="completed",
            payload_json={"status": "completed"},
        )
    )
    appender.append_status_event(
        SampleStatusEventRow(
            id=UUID(int=10),
            sample_id=sample_id,
            event_timestamp=base_time + timedelta(seconds=5),
            event_type="sample.status_changed",
            status="completed",
        )
    )

    state = reconstruct_sample_runtime_state_at(session, sample_id=sample_id)

    assert state.status == "completed"
    assert state.tasks[task_id].task_slug == "root"
    assert state.tasks[task_id].status == "completed"
    assert state.tasks[task_id].task_snapshot_json == {"slug": "root"}
    assert state.edges[edge_id].source_task_id == task_id
    assert state.workers[task_id].worker_snapshot_json == {"slug": "root-worker"}
    assert state.evaluators_by_task_id[task_id][0].evaluator_slug == "default"
    assert state.sandboxes[task_id].sandbox_slug == "ubuntu"
    assert state.annotations[("task", task_id, "review")].payload_json == {
        "value": {"label": "important"}
    }


def test_replay_can_stop_at_timestamp_slice(session: Session) -> None:
    sample_id = uuid4()
    task_id = uuid4()
    base_time = datetime(2026, 5, 25, 12, 0, tzinfo=UTC)
    appender = SampleRuntimeEventAppender(session)

    appender.append_task_event(
        SampleTaskEventRow(
            sample_id=sample_id,
            event_timestamp=base_time,
            event_type="task.added",
            task_id=task_id,
            task_slug="root",
            status="pending",
        )
    )
    appender.append_task_event(
        SampleTaskEventRow(
            sample_id=sample_id,
            event_timestamp=base_time + timedelta(seconds=1),
            event_type="task.removed",
            task_id=task_id,
            task_slug="root",
        )
    )

    before_remove = reconstruct_sample_runtime_state_at(
        session,
        sample_id=sample_id,
        at=base_time,
    )
    after_remove = reconstruct_sample_runtime_state_at(session, sample_id=sample_id)

    assert task_id in before_remove.tasks
    assert task_id not in after_remove.tasks
