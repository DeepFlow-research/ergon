from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlmodel import SQLModel, Session, create_engine, select

from ergon_core.core.persistence.samples.models import SampleAnnotationEventRow
from ergon_core.core.persistence.telemetry.models import SampleRecord
from ergon_core.core.application.samples.events import SampleRuntimeEventAppender

_REGISTERED_TABLE_MODELS = (SampleRecord,)


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_annotation_set_update_and_delete_use_annotation_wal(session: Session) -> None:
    sample_id = uuid4()
    task_id = uuid4()
    appender = SampleRuntimeEventAppender(session)

    base_time = datetime(2026, 5, 25, 12, 0, tzinfo=UTC)

    for index, (event_type, payload) in enumerate(
        (
            ("annotation.set", {"value": {"label": "important"}}),
            ("annotation.updated", {"value": {"label": "routine"}}),
            ("annotation.deleted", {}),
        )
    ):
        appender.append_annotation_event(
            SampleAnnotationEventRow(
                sample_id=sample_id,
                event_timestamp=base_time + timedelta(seconds=index),
                target_type="task",
                target_id=task_id,
                key="review",
                event_type=event_type,
                payload_json=payload,
            )
        )

    rows = session.exec(
        select(SampleAnnotationEventRow).order_by(
            SampleAnnotationEventRow.event_timestamp,
            SampleAnnotationEventRow.id,
        )
    ).all()

    assert [row.event_type for row in rows] == [
        "annotation.set",
        "annotation.updated",
        "annotation.deleted",
    ]
    assert [row.key for row in rows] == ["review", "review", "review"]


def test_annotation_events_are_not_a_generic_sample_events_table() -> None:
    assert SampleAnnotationEventRow.__tablename__ == "sample_annotation_events"
    assert "sample_events" not in SQLModel.metadata.tables
