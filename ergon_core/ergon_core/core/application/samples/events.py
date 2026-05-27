"""Thin append helper for typed sample runtime WAL rows."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Literal, Protocol
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
from sqlmodel import Session, select

if TYPE_CHECKING:
    from ergon_core.core.application.samples.event_views import SampleRuntimeEventView

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
        return [sample_runtime_event_view_from_row(row) for row in rows]


def sample_runtime_event_view_from_row(row: SampleRuntimeEventRow) -> SampleRuntimeEventView:
    """Convert a typed WAL row into the public sample runtime event view."""
    from ergon_core.core.application.samples.event_views import (
        sample_runtime_event_from_row,
    )

    return sample_runtime_event_from_row(row)


_EVENT_MODELS = (
    SampleStatusEventRow,
    SampleTaskEventRow,
    SampleEdgeEventRow,
    SampleWorkerEventRow,
    SampleEvaluatorEventRow,
    SampleSandboxEventRow,
    SampleAnnotationEventRow,
)
