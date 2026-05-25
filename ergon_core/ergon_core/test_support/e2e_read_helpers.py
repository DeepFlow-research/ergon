"""Stable test-support reads for e2e smoke assertions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Mapping, cast
from uuid import UUID

from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import (
    SampleResource,
    SampleTaskEvaluation,
    SampleTaskAttempt,
    SandboxCommandWalEntry,
    SandboxEvent,
)
from pydantic import BaseModel, ConfigDict
from sqlmodel import select


@dataclass(frozen=True)
class ResourceSnapshot:
    name: str
    file_path: str
    content_hash: str | None
    kind: str
    created_at: datetime


@dataclass(frozen=True)
class TaskExecutionSnapshot:
    task_id: UUID
    started_at: datetime | None
    completed_at: datetime | None


@dataclass(frozen=True)
class TaskEvaluationSnapshot:
    score: float
    created_at: datetime


@dataclass(frozen=True)
class SandboxCommandWalSnapshot:
    command: str


@dataclass(frozen=True)
class SandboxEventSnapshot:
    sandbox_id: str
    kind: str


class ObservedSampleRuntimeEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    event_timestamp: datetime
    event_type: str
    event_table: Literal[
        "sample_status_events",
        "sample_task_events",
        "sample_edge_events",
        "sample_worker_events",
        "sample_evaluator_events",
        "sample_sandbox_events",
        "sample_annotation_events",
    ]
    task_slug: str | None = None
    source_task_slug: str | None = None
    target_task_slug: str | None = None
    status: str | None = None
    worker_slug: str | None = None
    evaluator_slug: str | None = None
    sandbox_slug: str | None = None
    annotation_key: str | None = None


class ObservedSampleRuntimeEventStream(BaseModel):
    model_config = ConfigDict(frozen=True)

    ordered_events: tuple[ObservedSampleRuntimeEvent, ...]
    status_sequence: tuple[str, ...]
    task_added_slugs: tuple[str, ...]
    task_terminal_status_by_slug: dict[str, str]
    edge_added_pairs: tuple[tuple[str, str], ...]
    worker_added_by_task_slug: dict[str, str]
    evaluator_added_by_task_slug: dict[str, tuple[str, ...]]
    sandbox_added_by_task_slug: dict[str, str]
    annotation_keys_by_task_slug: dict[str, tuple[str, ...]]

    @classmethod
    def from_ordered_events(
        cls,
        ordered_events: tuple[ObservedSampleRuntimeEvent, ...],
    ) -> "ObservedSampleRuntimeEventStream":
        task_terminal_status_by_slug: dict[str, str] = {}
        worker_added_by_task_slug: dict[str, str] = {}
        evaluator_added_by_task_slug: dict[str, list[str]] = {}
        sandbox_added_by_task_slug: dict[str, str] = {}
        annotation_keys_by_task_slug: dict[str, list[str]] = {}

        for event in ordered_events:
            if event.event_type == "task.status_changed" and event.task_slug and event.status:
                task_terminal_status_by_slug[event.task_slug] = event.status
            if event.event_type == "worker.added" and event.task_slug and event.worker_slug:
                worker_added_by_task_slug[event.task_slug] = event.worker_slug
            if event.event_type == "evaluator.added" and event.task_slug and event.evaluator_slug:
                evaluator_added_by_task_slug.setdefault(event.task_slug, []).append(
                    event.evaluator_slug
                )
            if event.event_type == "sandbox.added" and event.task_slug and event.sandbox_slug:
                sandbox_added_by_task_slug[event.task_slug] = event.sandbox_slug
            if (
                event.event_type.startswith("annotation.")
                and event.task_slug
                and event.annotation_key
            ):
                annotation_keys_by_task_slug.setdefault(event.task_slug, []).append(
                    event.annotation_key
                )

        return cls(
            ordered_events=ordered_events,
            status_sequence=tuple(
                event.status
                for event in ordered_events
                if event.event_type == "sample.status_changed" and event.status
            ),
            task_added_slugs=tuple(
                event.task_slug
                for event in ordered_events
                if event.event_type == "task.added" and event.task_slug
            ),
            task_terminal_status_by_slug=task_terminal_status_by_slug,
            edge_added_pairs=tuple(
                (event.source_task_slug, event.target_task_slug)
                for event in ordered_events
                if event.event_type == "edge.added"
                and event.source_task_slug
                and event.target_task_slug
            ),
            worker_added_by_task_slug=worker_added_by_task_slug,
            evaluator_added_by_task_slug={
                task_slug: tuple(evaluator_slugs)
                for task_slug, evaluator_slugs in evaluator_added_by_task_slug.items()
            },
            sandbox_added_by_task_slug=sandbox_added_by_task_slug,
            annotation_keys_by_task_slug={
                task_slug: tuple(annotation_keys)
                for task_slug, annotation_keys in annotation_keys_by_task_slug.items()
            },
        )


def _resource_snapshot(row: SampleResource) -> ResourceSnapshot:
    return ResourceSnapshot(
        name=row.name,
        file_path=row.file_path,
        content_hash=row.content_hash,
        kind=row.kind,
        created_at=row.created_at,
    )


def _execution_snapshot(row: SampleTaskAttempt) -> TaskExecutionSnapshot:
    return TaskExecutionSnapshot(
        task_id=row.task_id,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def _evaluation_snapshot(row: SampleTaskEvaluation) -> TaskEvaluationSnapshot:
    return TaskEvaluationSnapshot(score=row.score, created_at=row.created_at)


def read_resource_bytes(resource: ResourceSnapshot) -> bytes:
    return Path(resource.file_path).read_bytes()


def first_probe_resource(sample_id: UUID) -> ResourceSnapshot | None:
    with get_session() as session:
        row = session.exec(
            select(SampleResource)
            .where(SampleResource.sample_id == sample_id)
            .where(
                SampleResource.name.like("probe_%.json"),  # ty: ignore[unresolved-attribute]
            )
            .where(SampleResource.kind == "report")
            .order_by(
                SampleResource.created_at,  # ty: ignore[unresolved-attribute]
            )
            .limit(1),
        ).first()
    return None if row is None else _resource_snapshot(row)


def list_named_resources(
    sample_id: UUID,
    *,
    prefix: str,
    suffix: str,
) -> list[ResourceSnapshot]:
    with get_session() as session:
        rows = list(
            session.exec(
                select(SampleResource)
                .where(SampleResource.sample_id == sample_id)
                .where(
                    SampleResource.name.like(f"{prefix}%{suffix}"),  # ty: ignore[unresolved-attribute]
                ),
            ).all(),
        )
    return [_resource_snapshot(row) for row in rows]


def list_root_execution_and_evaluations(
    sample_id: UUID,
) -> tuple[TaskExecutionSnapshot | None, list[TaskEvaluationSnapshot]]:
    with get_session() as session:
        root = session.exec(
            select(SampleGraphNode)
            .where(SampleGraphNode.sample_id == sample_id)
            .where(SampleGraphNode.level == 0),
        ).one()
        execution = session.exec(
            select(SampleTaskAttempt).where(SampleTaskAttempt.task_id == root.task_id),
        ).first()
        evaluations = list(
            session.exec(
                select(SampleTaskEvaluation)
                .where(SampleTaskEvaluation.sample_id == sample_id)
                .where(SampleTaskEvaluation.task_id == root.task_id),
            ).all(),
        )
    execution_snapshot = None if execution is None else _execution_snapshot(execution)
    return execution_snapshot, [_evaluation_snapshot(row) for row in evaluations]


def list_sandbox_command_wal(sample_id: UUID) -> list[SandboxCommandWalSnapshot]:
    with get_session() as session:
        rows = list(
            session.exec(
                select(SandboxCommandWalEntry).where(SandboxCommandWalEntry.sample_id == sample_id),
            ).all(),
        )
    return [SandboxCommandWalSnapshot(command=row.command) for row in rows]


def list_sandbox_events(sample_id: UUID) -> list[SandboxEventSnapshot]:
    with get_session() as session:
        rows = list(
            session.exec(select(SandboxEvent).where(SandboxEvent.sample_id == sample_id)).all()
        )
    return [SandboxEventSnapshot(sandbox_id=row.sandbox_id, kind=row.kind) for row in rows]


def row_to_observed_sample_runtime_event(
    row: Any,  # slopcop: ignore[no-typing-any]
    *,
    task_slug_by_id: Mapping[UUID, str],
) -> ObservedSampleRuntimeEvent:
    # slopcop: ignore[no-hasattr-getattr]
    payload = _json_mapping(getattr(row, "payload_json", {}))
    # slopcop: ignore[no-hasattr-getattr]
    source_task_id = getattr(row, "source_task_id", None)
    # slopcop: ignore[no-hasattr-getattr]
    target_task_id = getattr(row, "target_task_id", None)
    # slopcop: ignore[no-hasattr-getattr]
    annotation_key = getattr(row, "key", None)
    return ObservedSampleRuntimeEvent(
        id=row.id,
        event_timestamp=row.event_timestamp,
        event_table=row.__tablename__,
        event_type=row.event_type,
        task_slug=_task_slug(row, payload, task_slug_by_id),
        source_task_slug=task_slug_by_id.get(source_task_id),
        target_task_slug=task_slug_by_id.get(target_task_id),
        status=_string_attr_or_payload(row, payload, "status"),
        worker_slug=_slug_attr_or_payload(row, payload, "worker"),
        evaluator_slug=_slug_attr_or_payload(row, payload, "evaluator"),
        sandbox_slug=_slug_attr_or_payload(row, payload, "sandbox"),
        annotation_key=annotation_key,
    )


def read_sample_runtime_event_stream(sample_id: UUID) -> ObservedSampleRuntimeEventStream:
    (
        SampleStatusEventRow,
        SampleTaskEventRow,
        SampleEdgeEventRow,
        SampleWorkerEventRow,
        SampleEvaluatorEventRow,
        SampleSandboxEventRow,
        SampleAnnotationEventRow,
    ) = _sample_runtime_event_row_classes()

    with get_session() as session:
        task_rows = list(
            session.exec(
                select(SampleTaskEventRow)
                .where(SampleTaskEventRow.sample_id == sample_id)
                .order_by(SampleTaskEventRow.event_timestamp, SampleTaskEventRow.id)
            ).all(),
        )
        task_slug_by_id = _task_slug_by_id_from_task_events(task_rows)
        event_rows = (
            session.exec(
                select(SampleStatusEventRow).where(SampleStatusEventRow.sample_id == sample_id)
            ).all(),
            task_rows,
            session.exec(
                select(SampleEdgeEventRow).where(SampleEdgeEventRow.sample_id == sample_id)
            ).all(),
            session.exec(
                select(SampleWorkerEventRow).where(SampleWorkerEventRow.sample_id == sample_id)
            ).all(),
            session.exec(
                select(SampleEvaluatorEventRow).where(
                    SampleEvaluatorEventRow.sample_id == sample_id
                )
            ).all(),
            session.exec(
                select(SampleSandboxEventRow).where(SampleSandboxEventRow.sample_id == sample_id)
            ).all(),
            session.exec(
                select(SampleAnnotationEventRow).where(
                    SampleAnnotationEventRow.sample_id == sample_id
                )
            ).all(),
        )

    events = [
        row_to_observed_sample_runtime_event(row, task_slug_by_id=task_slug_by_id)
        for rows in event_rows
        for row in rows
    ]
    ordered_events = tuple(sorted(events, key=lambda event: (event.event_timestamp, event.id)))
    return ObservedSampleRuntimeEventStream.from_ordered_events(ordered_events)


def leaf_execution_timings_by_slug(sample_id: UUID) -> dict[str, TaskExecutionSnapshot | None]:
    with get_session() as session:
        leaves = list(
            session.exec(
                select(SampleGraphNode)
                .where(SampleGraphNode.sample_id == sample_id)
                .where(SampleGraphNode.level > 0),
            ).all(),
        )
        executions = list(
            session.exec(
                select(SampleTaskAttempt)
                .where(SampleTaskAttempt.sample_id == sample_id)
                .where(
                    SampleTaskAttempt.task_id.in_([leaf.task_id for leaf in leaves]),  # ty: ignore[unresolved-attribute]
                ),
            ).all(),
        )

    by_task = {execution.task_id: _execution_snapshot(execution) for execution in executions}
    return {leaf.task_slug: by_task.get(leaf.task_id) for leaf in leaves}


def _sample_runtime_event_row_classes() -> tuple[type[Any], ...]:  # slopcop: ignore[no-typing-any]
    from ergon_core.core.persistence.samples.models import (
        SampleAnnotationEventRow,
        SampleEdgeEventRow,
        SampleEvaluatorEventRow,
        SampleSandboxEventRow,
        SampleStatusEventRow,
        SampleTaskEventRow,
        SampleWorkerEventRow,
    )

    return (
        SampleStatusEventRow,
        SampleTaskEventRow,
        SampleEdgeEventRow,
        SampleWorkerEventRow,
        SampleEvaluatorEventRow,
        SampleSandboxEventRow,
        SampleAnnotationEventRow,
    )


def _task_slug_by_id_from_task_events(
    task_rows: list[Any],
) -> dict[UUID, str]:  # slopcop: ignore[no-typing-any]
    task_slug_by_id: dict[UUID, str] = {}
    for row in task_rows:
        if row.event_type != "task.added":
            continue
        # slopcop: ignore[no-hasattr-getattr]
        payload = _json_mapping(getattr(row, "payload_json", {}))
        task_slug = _task_slug(row, payload, task_slug_by_id)
        if task_slug:
            task_slug_by_id[row.task_id] = task_slug
    return task_slug_by_id


def _task_slug(
    row: Any,  # slopcop: ignore[no-typing-any]
    payload: Mapping[str, Any],  # slopcop: ignore[no-typing-any]
    task_slug_by_id: Mapping[UUID, str],
) -> str | None:
    # slopcop: ignore[no-hasattr-getattr]
    task_id = getattr(row, "task_id", None)
    if task_id is None:
        # slopcop: ignore[no-hasattr-getattr]
        task_id = getattr(row, "target_id", None)
    return (
        task_slug_by_id.get(task_id)
        or _string_attr_or_payload(row, payload, "task_slug")
        or _string_payload(payload, "task_key")
        or _string_payload(payload, "target_key")
    )


def _slug_attr_or_payload(
    row: Any,  # slopcop: ignore[no-typing-any]
    payload: Mapping[str, Any],  # slopcop: ignore[no-typing-any]
    name: str,
) -> str | None:
    attr_value = getattr(row, f"{name}_slug", None)  # slopcop: ignore[no-hasattr-getattr]
    if isinstance(attr_value, str):
        return attr_value
    direct = _string_payload(payload, f"{name}_slug")
    if direct is not None:
        return direct
    nested = payload.get(name)
    if isinstance(nested, Mapping):
        return _string_payload(nested, "slug")
    snapshot = getattr(row, f"{name}_snapshot_json", None)  # slopcop: ignore[no-hasattr-getattr]
    if isinstance(snapshot, Mapping):
        return _string_payload(snapshot, "slug")
    return None


def _string_attr_or_payload(
    row: Any,  # slopcop: ignore[no-typing-any]
    payload: Mapping[str, Any],  # slopcop: ignore[no-typing-any]
    name: str,
) -> str | None:
    attr_value = getattr(row, name, None)  # slopcop: ignore[no-hasattr-getattr]
    if isinstance(attr_value, str):
        return attr_value
    return _string_payload(payload, name)


def _string_payload(
    payload: Mapping[str, Any], key: str
) -> str | None:  # slopcop: ignore[no-typing-any]
    value = payload.get(key)
    return value if isinstance(value, str) else None


def _json_mapping(value: object) -> Mapping[str, Any]:  # slopcop: ignore[no-typing-any]
    return cast(Mapping[str, Any], value) if isinstance(value, Mapping) else {}
