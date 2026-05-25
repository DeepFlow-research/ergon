"""Typed append-only sample runtime event tables."""

from datetime import datetime
from uuid import UUID, uuid4

from ergon_core.core.shared.utils import utcnow as _utcnow
from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel

TZDateTime = DateTime(timezone=True)


class SampleStatusEventRow(SQLModel, table=True):
    __tablename__ = "sample_status_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sample_id: UUID = Field(foreign_key="samples.id", index=True)
    event_timestamp: datetime = Field(default_factory=_utcnow, index=True, sa_type=TZDateTime)
    event_type: str = Field(index=True, description="Typed sample lifecycle event name.")
    status: str = Field(index=True, description="Sample status after this event applies.")
    actor: str | None = Field(default=None, index=True)
    payload_json: dict = Field(default_factory=dict, sa_column=Column(JSON))


class SampleTaskEventRow(SQLModel, table=True):
    __tablename__ = "sample_task_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sample_id: UUID = Field(foreign_key="samples.id", index=True)
    task_id: UUID = Field(index=True)
    task_slug: str | None = Field(default=None, index=True)
    event_timestamp: datetime = Field(default_factory=_utcnow, index=True, sa_type=TZDateTime)
    event_type: str = Field(index=True, description="Typed task graph event name.")
    status: str | None = Field(default=None, index=True)
    task_snapshot_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    actor: str | None = Field(default=None, index=True)
    payload_json: dict = Field(default_factory=dict, sa_column=Column(JSON))


class SampleEdgeEventRow(SQLModel, table=True):
    __tablename__ = "sample_edge_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sample_id: UUID = Field(foreign_key="samples.id", index=True)
    edge_id: UUID = Field(index=True)
    source_task_id: UUID = Field(index=True)
    target_task_id: UUID = Field(index=True)
    event_timestamp: datetime = Field(default_factory=_utcnow, index=True, sa_type=TZDateTime)
    event_type: str = Field(index=True, description="Typed task-edge event name.")
    status: str | None = Field(default=None, index=True)
    edge_snapshot_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    actor: str | None = Field(default=None, index=True)
    payload_json: dict = Field(default_factory=dict, sa_column=Column(JSON))


class SampleWorkerEventRow(SQLModel, table=True):
    __tablename__ = "sample_worker_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sample_id: UUID = Field(foreign_key="samples.id", index=True)
    task_id: UUID | None = Field(default=None, index=True)
    worker_slug: str = Field(index=True)
    worker_type: str | None = Field(default=None, index=True)
    model_target: str | None = Field(default=None, index=True)
    worker_snapshot_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    event_timestamp: datetime = Field(default_factory=_utcnow, index=True, sa_type=TZDateTime)
    event_type: str = Field(index=True, description="Typed worker membership event name.")
    actor: str | None = Field(default=None, index=True)
    payload_json: dict = Field(default_factory=dict, sa_column=Column(JSON))


class SampleEvaluatorEventRow(SQLModel, table=True):
    __tablename__ = "sample_evaluator_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sample_id: UUID = Field(foreign_key="samples.id", index=True)
    task_id: UUID | None = Field(default=None, index=True)
    evaluator_slug: str = Field(index=True)
    evaluator_type: str | None = Field(default=None, index=True)
    evaluator_snapshot_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    event_timestamp: datetime = Field(default_factory=_utcnow, index=True, sa_type=TZDateTime)
    event_type: str = Field(index=True, description="Typed evaluator membership event name.")
    actor: str | None = Field(default=None, index=True)
    payload_json: dict = Field(default_factory=dict, sa_column=Column(JSON))


class SampleSandboxEventRow(SQLModel, table=True):
    __tablename__ = "sample_sandbox_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sample_id: UUID = Field(foreign_key="samples.id", index=True)
    task_id: UUID | None = Field(default=None, index=True)
    sandbox_slug: str = Field(index=True)
    sandbox_type: str | None = Field(default=None, index=True)
    sandbox_snapshot_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    event_timestamp: datetime = Field(default_factory=_utcnow, index=True, sa_type=TZDateTime)
    event_type: str = Field(index=True, description="Typed sandbox membership event name.")
    actor: str | None = Field(default=None, index=True)
    payload_json: dict = Field(default_factory=dict, sa_column=Column(JSON))


class SampleAnnotationEventRow(SQLModel, table=True):
    __tablename__ = "sample_annotation_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sample_id: UUID = Field(foreign_key="samples.id", index=True)
    target_type: str = Field(index=True)
    target_id: UUID = Field(index=True)
    key: str = Field(index=True)
    event_type: str = Field(index=True, description="Typed annotation event name.")
    event_timestamp: datetime = Field(default_factory=_utcnow, index=True, sa_type=TZDateTime)
    payload_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
