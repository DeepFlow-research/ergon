"""Canonical public views for typed sample runtime WAL events."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, get_args
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ergon_core.core.application.samples.events import (
    SampleAnnotationEventKind,
    SampleEdgeEventKind,
    SampleEvaluatorEventKind,
    SampleSandboxEventKind,
    SampleStatusEventKind,
    SampleTaskEventKind,
    SampleWorkerEventKind,
)
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


ALL_SAMPLE_RUNTIME_EVENT_TYPES = {
    "sample.status_changed",
    "task.added",
    "task.removed",
    "task.status_changed",
    "edge.added",
    "edge.removed",
    "edge.status_changed",
    "worker.added",
    "worker.removed",
    "evaluator.added",
    "evaluator.removed",
    "sandbox.added",
    "sandbox.removed",
    "annotation.set",
    "annotation.updated",
    "annotation.deleted",
}
RAW_PAYLOAD_DESCRIPTION = (
    "Raw typed WAL payload retained for diagnostics and forward compatibility."
)

ROW_MODEL_EVENT_TYPES: set[str] = set().union(
    get_args(SampleStatusEventKind),
    get_args(SampleTaskEventKind),
    get_args(SampleEdgeEventKind),
    get_args(SampleWorkerEventKind),
    get_args(SampleEvaluatorEventKind),
    get_args(SampleSandboxEventKind),
    get_args(SampleAnnotationEventKind),
)


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class SampleEventBase(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)

    event_id: UUID
    sample_id: UUID
    timestamp: datetime


class SampleStatusChangedEventView(SampleEventBase):
    event_type: Literal["sample.status_changed"]
    target_type: Literal["sample"]
    target_id: UUID
    status: str
    actor: str | None = None
    payload: JsonObject = Field(default_factory=dict, description=RAW_PAYLOAD_DESCRIPTION)


class SampleTaskAddedEventView(SampleEventBase):
    event_type: Literal["task.added"]
    target_type: Literal["task"]
    target_id: UUID
    task_slug: str | None = None
    status: str | None = None
    task: JsonObject = Field(default_factory=dict)
    actor: str | None = None
    payload: JsonObject = Field(default_factory=dict, description=RAW_PAYLOAD_DESCRIPTION)


class SampleTaskRemovedEventView(SampleEventBase):
    event_type: Literal["task.removed"]
    target_type: Literal["task"]
    target_id: UUID
    task_slug: str | None = None
    actor: str | None = None
    payload: JsonObject = Field(default_factory=dict, description=RAW_PAYLOAD_DESCRIPTION)


class SampleTaskStatusChangedEventView(SampleEventBase):
    event_type: Literal["task.status_changed"]
    target_type: Literal["task"]
    target_id: UUID
    task_slug: str | None = None
    status: str
    actor: str | None = None
    payload: JsonObject = Field(default_factory=dict, description=RAW_PAYLOAD_DESCRIPTION)


class SampleEdgeAddedEventView(SampleEventBase):
    event_type: Literal["edge.added"]
    target_type: Literal["edge"]
    target_id: UUID
    source_task_id: UUID
    target_task_id: UUID
    status: str | None = None
    edge: JsonObject = Field(default_factory=dict)
    actor: str | None = None
    payload: JsonObject = Field(default_factory=dict, description=RAW_PAYLOAD_DESCRIPTION)


class SampleEdgeRemovedEventView(SampleEventBase):
    event_type: Literal["edge.removed"]
    target_type: Literal["edge"]
    target_id: UUID
    source_task_id: UUID
    target_task_id: UUID
    actor: str | None = None
    payload: JsonObject = Field(default_factory=dict, description=RAW_PAYLOAD_DESCRIPTION)


class SampleEdgeStatusChangedEventView(SampleEventBase):
    event_type: Literal["edge.status_changed"]
    target_type: Literal["edge"]
    target_id: UUID
    source_task_id: UUID
    target_task_id: UUID
    status: str
    actor: str | None = None
    payload: JsonObject = Field(default_factory=dict, description=RAW_PAYLOAD_DESCRIPTION)


class SampleWorkerAddedEventView(SampleEventBase):
    event_type: Literal["worker.added"]
    target_type: Literal["task"]
    target_id: UUID | None = None
    worker_slug: str
    worker_type: str | None = None
    model_target: str | None = None
    worker: JsonObject = Field(default_factory=dict)
    actor: str | None = None
    payload: JsonObject = Field(default_factory=dict, description=RAW_PAYLOAD_DESCRIPTION)


class SampleWorkerRemovedEventView(SampleEventBase):
    event_type: Literal["worker.removed"]
    target_type: Literal["task"]
    target_id: UUID | None = None
    worker_slug: str
    actor: str | None = None
    payload: JsonObject = Field(default_factory=dict, description=RAW_PAYLOAD_DESCRIPTION)


class SampleEvaluatorAddedEventView(SampleEventBase):
    event_type: Literal["evaluator.added"]
    target_type: Literal["task"]
    target_id: UUID | None = None
    evaluator_slug: str
    evaluator_type: str | None = None
    evaluator: JsonObject = Field(default_factory=dict)
    actor: str | None = None
    payload: JsonObject = Field(default_factory=dict, description=RAW_PAYLOAD_DESCRIPTION)


class SampleEvaluatorRemovedEventView(SampleEventBase):
    event_type: Literal["evaluator.removed"]
    target_type: Literal["task"]
    target_id: UUID | None = None
    evaluator_slug: str
    actor: str | None = None
    payload: JsonObject = Field(default_factory=dict, description=RAW_PAYLOAD_DESCRIPTION)


class SampleSandboxAddedEventView(SampleEventBase):
    event_type: Literal["sandbox.added"]
    target_type: Literal["task"]
    target_id: UUID | None = None
    sandbox_slug: str
    sandbox_type: str | None = None
    sandbox: JsonObject = Field(default_factory=dict)
    actor: str | None = None
    payload: JsonObject = Field(default_factory=dict, description=RAW_PAYLOAD_DESCRIPTION)


class SampleSandboxRemovedEventView(SampleEventBase):
    event_type: Literal["sandbox.removed"]
    target_type: Literal["task"]
    target_id: UUID | None = None
    sandbox_slug: str
    actor: str | None = None
    payload: JsonObject = Field(default_factory=dict, description=RAW_PAYLOAD_DESCRIPTION)


class SampleAnnotationSetEventView(SampleEventBase):
    event_type: Literal["annotation.set"]
    target_type: str
    target_id: UUID
    key: str
    value: JsonObject = Field(default_factory=dict)
    payload: JsonObject = Field(default_factory=dict, description=RAW_PAYLOAD_DESCRIPTION)


class SampleAnnotationUpdatedEventView(SampleEventBase):
    event_type: Literal["annotation.updated"]
    target_type: str
    target_id: UUID
    key: str
    value: JsonObject = Field(default_factory=dict)
    payload: JsonObject = Field(default_factory=dict, description=RAW_PAYLOAD_DESCRIPTION)


class SampleAnnotationDeletedEventView(SampleEventBase):
    event_type: Literal["annotation.deleted"]
    target_type: str
    target_id: UUID
    key: str
    payload: JsonObject = Field(default_factory=dict, description=RAW_PAYLOAD_DESCRIPTION)


SampleRuntimeEventView = Annotated[
    SampleStatusChangedEventView
    | SampleTaskAddedEventView
    | SampleTaskRemovedEventView
    | SampleTaskStatusChangedEventView
    | SampleEdgeAddedEventView
    | SampleEdgeRemovedEventView
    | SampleEdgeStatusChangedEventView
    | SampleWorkerAddedEventView
    | SampleWorkerRemovedEventView
    | SampleEvaluatorAddedEventView
    | SampleEvaluatorRemovedEventView
    | SampleSandboxAddedEventView
    | SampleSandboxRemovedEventView
    | SampleAnnotationSetEventView
    | SampleAnnotationUpdatedEventView
    | SampleAnnotationDeletedEventView,
    Field(discriminator="event_type"),
]
VIEW_EVENT_TYPES = ALL_SAMPLE_RUNTIME_EVENT_TYPES


SampleRuntimeEventRow = (
    SampleStatusEventRow
    | SampleTaskEventRow
    | SampleEdgeEventRow
    | SampleWorkerEventRow
    | SampleEvaluatorEventRow
    | SampleSandboxEventRow
    | SampleAnnotationEventRow
)


EventViewFields = dict[str, object]


def _event_common(row: SampleRuntimeEventRow) -> EventViewFields:
    return {
        "event_id": row.id,
        "sample_id": row.sample_id,
        "event_type": row.event_type,
        "timestamp": row.event_timestamp,
        "payload": dict(row.payload_json),
    }


def _task_event_from_row(
    row: SampleTaskEventRow,
    common: EventViewFields,
) -> SampleTaskAddedEventView | SampleTaskRemovedEventView | SampleTaskStatusChangedEventView:
    fields = dict(
        common,
        target_type="task",
        target_id=row.task_id,
        task_slug=row.task_slug,
        actor=row.actor,
    )
    if row.event_type == "task.added":
        return SampleTaskAddedEventView(
            **fields,
            status=row.status,
            task=row.task_snapshot_json,
        )
    if row.event_type == "task.removed":
        return SampleTaskRemovedEventView(**fields)
    return SampleTaskStatusChangedEventView(**fields, status=str(row.status))


def _edge_event_from_row(
    row: SampleEdgeEventRow,
    common: EventViewFields,
) -> SampleEdgeAddedEventView | SampleEdgeRemovedEventView | SampleEdgeStatusChangedEventView:
    fields = dict(
        common,
        target_type="edge",
        target_id=row.edge_id,
        source_task_id=row.source_task_id,
        target_task_id=row.target_task_id,
        actor=row.actor,
    )
    if row.event_type == "edge.added":
        return SampleEdgeAddedEventView(
            **fields,
            status=row.status,
            edge=row.edge_snapshot_json,
        )
    if row.event_type == "edge.removed":
        return SampleEdgeRemovedEventView(**fields)
    return SampleEdgeStatusChangedEventView(**fields, status=str(row.status))


def _worker_event_from_row(
    row: SampleWorkerEventRow,
    common: EventViewFields,
) -> SampleWorkerAddedEventView | SampleWorkerRemovedEventView:
    fields = dict(
        common,
        target_type="task",
        target_id=row.task_id,
        worker_slug=row.worker_slug,
        actor=row.actor,
    )
    if row.event_type == "worker.added":
        return SampleWorkerAddedEventView(
            **fields,
            worker_type=row.worker_type,
            model_target=row.model_target,
            worker=row.worker_snapshot_json,
        )
    return SampleWorkerRemovedEventView(**fields)


def _evaluator_event_from_row(
    row: SampleEvaluatorEventRow,
    common: EventViewFields,
) -> SampleEvaluatorAddedEventView | SampleEvaluatorRemovedEventView:
    fields = dict(
        common,
        target_type="task",
        target_id=row.task_id,
        evaluator_slug=row.evaluator_slug,
        actor=row.actor,
    )
    if row.event_type == "evaluator.added":
        return SampleEvaluatorAddedEventView(
            **fields,
            evaluator_type=row.evaluator_type,
            evaluator=row.evaluator_snapshot_json,
        )
    return SampleEvaluatorRemovedEventView(**fields)


def _sandbox_event_from_row(
    row: SampleSandboxEventRow,
    common: EventViewFields,
) -> SampleSandboxAddedEventView | SampleSandboxRemovedEventView:
    fields = dict(
        common,
        target_type="task",
        target_id=row.task_id,
        sandbox_slug=row.sandbox_slug,
        actor=row.actor,
    )
    if row.event_type == "sandbox.added":
        return SampleSandboxAddedEventView(
            **fields,
            sandbox_type=row.sandbox_type,
            sandbox=row.sandbox_snapshot_json,
        )
    return SampleSandboxRemovedEventView(**fields)


def _annotation_event_from_row(
    row: SampleAnnotationEventRow,
    common: EventViewFields,
) -> (
    SampleAnnotationSetEventView
    | SampleAnnotationUpdatedEventView
    | SampleAnnotationDeletedEventView
):
    value = row.payload_json.get("value")
    fields = dict(
        common,
        target_type=row.target_type,
        target_id=row.target_id,
        key=row.key,
    )
    if row.event_type == "annotation.set":
        return SampleAnnotationSetEventView(
            **fields,
            value=value if isinstance(value, dict) else {},
        )
    if row.event_type == "annotation.updated":
        return SampleAnnotationUpdatedEventView(
            **fields,
            value=value if isinstance(value, dict) else {},
        )
    return SampleAnnotationDeletedEventView(**fields)


def sample_runtime_event_from_row(row: SampleRuntimeEventRow) -> SampleRuntimeEventView:
    common = _event_common(row)
    if isinstance(row, SampleStatusEventRow):
        return SampleStatusChangedEventView(
            **common,
            target_type="sample",
            target_id=row.sample_id,
            status=row.status,
            actor=row.actor,
        )
    if isinstance(row, SampleTaskEventRow):
        return _task_event_from_row(row, common)
    if isinstance(row, SampleEdgeEventRow):
        return _edge_event_from_row(row, common)
    if isinstance(row, SampleWorkerEventRow):
        return _worker_event_from_row(row, common)
    if isinstance(row, SampleEvaluatorEventRow):
        return _evaluator_event_from_row(row, common)
    if isinstance(row, SampleSandboxEventRow):
        return _sandbox_event_from_row(row, common)
    return _annotation_event_from_row(row, common)
