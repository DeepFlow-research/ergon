"""Thin append helper and view DTOs for typed sample runtime WAL rows."""

from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from ergon_core.core.persistence.samples.models import (
    SampleAnnotationEventRow,
    SampleEdgeEventRow,
    SampleEvaluatorEventRow,
    SampleSandboxEventRow,
    SampleStatusEventRow,
    SampleTaskEventRow,
    SampleWorkerEventRow,
)
from ergon_core.core.shared.json_types import JsonObject
from ergon_core.core.shared.utils import utcnow
from pydantic import BaseModel, Field
from sqlmodel import Session, select

SampleStatusEventKind = Literal["sample.status_changed"]
SampleTaskEventKind = Literal["task.added", "task.removed", "task.status_changed"]
SampleEdgeEventKind = Literal["edge.added", "edge.removed", "edge.status_changed"]
SampleWorkerEventKind = Literal["worker.added", "worker.removed"]
SampleEvaluatorEventKind = Literal["evaluator.added", "evaluator.removed"]
SampleSandboxEventKind = Literal["sandbox.added", "sandbox.removed"]
SampleAnnotationEventKind = Literal[
    "annotation.set",
    "annotation.updated",
    "annotation.deleted",
]

SampleRuntimeEventRow = (
    SampleStatusEventRow
    | SampleTaskEventRow
    | SampleEdgeEventRow
    | SampleWorkerEventRow
    | SampleEvaluatorEventRow
    | SampleSandboxEventRow
    | SampleAnnotationEventRow
)


class SampleRuntimeEventView(BaseModel):
    model_config = {"frozen": True}

    id: UUID
    sample_id: UUID
    event_timestamp: datetime
    table: Literal[
        "sample_status_events",
        "sample_task_events",
        "sample_edge_events",
        "sample_worker_events",
        "sample_evaluator_events",
        "sample_sandbox_events",
        "sample_annotation_events",
    ]
    event_type: str
    target_type: str
    target_id: UUID | None
    payload: JsonObject = Field(
        default_factory=dict,
        description="Typed event payload copied from the source sample runtime WAL row.",
    )


class SampleRuntimeEventSubscriber(Protocol):
    async def __call__(self, event: SampleRuntimeEventRow) -> None: ...


class SampleRuntimeEventAppender:
    """Transaction-local append helper for already-decided typed WAL rows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def append_status_event(self, row: SampleStatusEventRow) -> SampleStatusEventRow:
        self._session.add(row)
        self._session.flush()
        return row

    def append_task_event(self, row: SampleTaskEventRow) -> SampleTaskEventRow:
        self._session.add(row)
        self._session.flush()
        return row

    def append_edge_event(self, row: SampleEdgeEventRow) -> SampleEdgeEventRow:
        self._session.add(row)
        self._session.flush()
        return row

    def append_worker_event(self, row: SampleWorkerEventRow) -> SampleWorkerEventRow:
        self._session.add(row)
        self._session.flush()
        return row

    def append_evaluator_event(self, row: SampleEvaluatorEventRow) -> SampleEvaluatorEventRow:
        self._session.add(row)
        self._session.flush()
        return row

    def append_sandbox_event(self, row: SampleSandboxEventRow) -> SampleSandboxEventRow:
        self._session.add(row)
        self._session.flush()
        return row

    def append_annotation_event(self, row: SampleAnnotationEventRow) -> SampleAnnotationEventRow:
        self._session.add(row)
        self._session.flush()
        return row


def append_sample_status_changed(
    session: Session,
    *,
    sample_id: UUID,
    status: str,
    actor: str,
    event_timestamp: datetime | None = None,
    payload: JsonObject | None = None,
) -> SampleStatusEventRow:
    return SampleRuntimeEventAppender(session).append_status_event(
        SampleStatusEventRow(
            sample_id=sample_id,
            event_type="sample.status_changed",
            status=status,
            actor=actor,
            event_timestamp=event_timestamp or utcnow(),
            payload_json=dict(payload or {}),
        )
    )


class SampleRuntimeEventReadService:
    def list_events(self, session: Session, sample_id: UUID) -> list[SampleRuntimeEventView]:
        rows: list[SampleRuntimeEventRow] = []
        for model in _EVENT_MODELS:
            rows.extend(session.exec(select(model).where(model.sample_id == sample_id)).all())
        rows.sort(key=lambda row: (row.event_timestamp, row.id))
        return [sample_runtime_event_from_row(row) for row in rows]


def sample_runtime_event_from_row(row: SampleRuntimeEventRow) -> SampleRuntimeEventView:
    table = row.__tablename__
    target_type, target_id = _target_for_row(row)
    payload = _payload_for_row(row)
    return SampleRuntimeEventView(
        id=row.id,
        sample_id=row.sample_id,
        event_timestamp=row.event_timestamp,
        table=table,
        event_type=row.event_type,
        target_type=target_type,
        target_id=target_id,
        payload=payload,
    )


def _target_for_row(row: SampleRuntimeEventRow) -> tuple[str, UUID | None]:
    if isinstance(row, SampleStatusEventRow):
        return "sample", row.sample_id
    if isinstance(row, SampleTaskEventRow):
        return "task", row.task_id
    if isinstance(row, SampleEdgeEventRow):
        return "edge", row.edge_id
    if isinstance(row, (SampleWorkerEventRow, SampleEvaluatorEventRow, SampleSandboxEventRow)):
        return "task", row.task_id
    return row.target_type, row.target_id


def _payload_for_row(row: SampleRuntimeEventRow) -> JsonObject:
    payload = dict(row.payload_json)
    if isinstance(row, SampleStatusEventRow):
        payload.setdefault("status", row.status)
    elif isinstance(row, SampleTaskEventRow):
        if row.task_slug is not None:
            payload.setdefault("task_slug", row.task_slug)
        if row.status is not None:
            payload.setdefault("status", row.status)
        payload.setdefault("task", row.task_snapshot_json)
    elif isinstance(row, SampleEdgeEventRow):
        if row.status is not None:
            payload.setdefault("status", row.status)
        payload.setdefault("source_task_id", str(row.source_task_id))
        payload.setdefault("target_task_id", str(row.target_task_id))
        payload.setdefault("edge", row.edge_snapshot_json)
    elif isinstance(row, SampleWorkerEventRow):
        payload.setdefault("worker", row.worker_snapshot_json)
        payload.setdefault("worker_slug", row.worker_slug)
    elif isinstance(row, SampleEvaluatorEventRow):
        payload.setdefault("evaluator", row.evaluator_snapshot_json)
        payload.setdefault("evaluator_slug", row.evaluator_slug)
    elif isinstance(row, SampleSandboxEventRow):
        payload.setdefault("sandbox", row.sandbox_snapshot_json)
        payload.setdefault("sandbox_slug", row.sandbox_slug)
    return payload


_EVENT_MODELS = (
    SampleStatusEventRow,
    SampleTaskEventRow,
    SampleEdgeEventRow,
    SampleWorkerEventRow,
    SampleEvaluatorEventRow,
    SampleSandboxEventRow,
    SampleAnnotationEventRow,
)
