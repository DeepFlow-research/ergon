"""Timestamp-sliced replay for typed sample runtime WAL rows."""

from datetime import datetime
from uuid import UUID

from ergon_core.core.application.samples.events import SampleRuntimeEventRow
from ergon_core.core.persistence.samples.models import (
    SampleAnnotationEventRow,
    SampleEdgeEventRow,
    SampleEvaluatorEventRow,
    SampleSandboxEventRow,
    SampleStatusEventRow,
    SampleTaskEventRow,
    SampleWorkerEventRow,
)
from pydantic import BaseModel, Field
from sqlmodel import Session, select


class SampleTaskRuntimeState(BaseModel):
    model_config = {"frozen": True}

    task_id: UUID
    task_slug: str | None = None
    status: str | None = None
    task_snapshot_json: dict = Field(default_factory=dict)


class SampleEdgeRuntimeState(BaseModel):
    model_config = {"frozen": True}

    edge_id: UUID
    source_task_id: UUID
    target_task_id: UUID
    status: str | None = None
    edge_snapshot_json: dict = Field(default_factory=dict)


class SampleWorkerRuntimeState(BaseModel):
    model_config = {"frozen": True}

    task_id: UUID
    worker_slug: str
    worker_snapshot_json: dict = Field(default_factory=dict)


class SampleEvaluatorRuntimeState(BaseModel):
    model_config = {"frozen": True}

    task_id: UUID
    evaluator_slug: str
    evaluator_snapshot_json: dict = Field(default_factory=dict)


class SampleSandboxRuntimeState(BaseModel):
    model_config = {"frozen": True}

    task_id: UUID
    sandbox_slug: str
    sandbox_snapshot_json: dict = Field(default_factory=dict)


class SampleAnnotationRuntimeState(BaseModel):
    model_config = {"frozen": True}

    target_type: str
    target_id: UUID
    key: str
    payload_json: dict = Field(default_factory=dict)


class SampleRuntimeState(BaseModel):
    model_config = {"frozen": True}

    status: str | None = None
    tasks: dict[UUID, SampleTaskRuntimeState] = Field(default_factory=dict)
    edges: dict[UUID, SampleEdgeRuntimeState] = Field(default_factory=dict)
    workers: dict[UUID, SampleWorkerRuntimeState] = Field(default_factory=dict)
    evaluators_by_task_id: dict[UUID, list[SampleEvaluatorRuntimeState]] = Field(
        default_factory=dict
    )
    sandboxes: dict[UUID, SampleSandboxRuntimeState] = Field(default_factory=dict)
    annotations: dict[tuple[str, UUID, str], SampleAnnotationRuntimeState] = Field(
        default_factory=dict
    )

    @classmethod
    def from_events(cls, rows: list[SampleRuntimeEventRow]) -> "SampleRuntimeState":
        accumulator = _SampleRuntimeStateAccumulator()
        for row in rows:
            accumulator.apply(row)
        return accumulator.to_state()


class _SampleRuntimeStateAccumulator:
    def __init__(self) -> None:
        self.status: str | None = None
        self.tasks: dict[UUID, SampleTaskRuntimeState] = {}
        self.edges: dict[UUID, SampleEdgeRuntimeState] = {}
        self.workers: dict[UUID, SampleWorkerRuntimeState] = {}
        self.evaluators_by_task_id: dict[UUID, list[SampleEvaluatorRuntimeState]] = {}
        self.sandboxes: dict[UUID, SampleSandboxRuntimeState] = {}
        self.annotations: dict[tuple[str, UUID, str], SampleAnnotationRuntimeState] = {}

    def apply(self, row: SampleRuntimeEventRow) -> None:
        if isinstance(row, SampleStatusEventRow):
            self.status = row.status
        elif isinstance(row, SampleTaskEventRow):
            self._apply_task(row)
        elif isinstance(row, SampleEdgeEventRow):
            self._apply_edge(row)
        elif isinstance(row, SampleWorkerEventRow) and row.task_id is not None:
            self._apply_worker(row)
        elif isinstance(row, SampleEvaluatorEventRow) and row.task_id is not None:
            self._apply_evaluator(row)
        elif isinstance(row, SampleSandboxEventRow) and row.task_id is not None:
            self._apply_sandbox(row)
        elif isinstance(row, SampleAnnotationEventRow):
            self._apply_annotation(row)

    def _apply_task(self, row: SampleTaskEventRow) -> None:
        if row.event_type == "task.removed":
            self.tasks.pop(row.task_id, None)
            return
        if row.event_type == "task.added":
            self.tasks[row.task_id] = SampleTaskRuntimeState(
                task_id=row.task_id,
                task_slug=row.task_slug,
                status=row.status,
                task_snapshot_json=dict(row.task_snapshot_json),
            )
            return
        if row.event_type == "task.status_changed":
            current = self.tasks.get(row.task_id)
            self.tasks[row.task_id] = SampleTaskRuntimeState(
                task_id=row.task_id,
                task_slug=_task_slug_from_event(row, current),
                status=row.status,
                task_snapshot_json=dict(
                    row.task_snapshot_json
                    or (current.task_snapshot_json if current is not None else {})
                ),
            )

    def _apply_edge(self, row: SampleEdgeEventRow) -> None:
        if row.event_type == "edge.removed":
            self.edges.pop(row.edge_id, None)
            return
        if row.event_type == "edge.added":
            self.edges[row.edge_id] = SampleEdgeRuntimeState(
                edge_id=row.edge_id,
                source_task_id=row.source_task_id,
                target_task_id=row.target_task_id,
                status=row.status,
                edge_snapshot_json=dict(row.edge_snapshot_json),
            )
            return
        if row.event_type == "edge.status_changed" and row.edge_id in self.edges:
            current_edge = self.edges[row.edge_id]
            self.edges[row.edge_id] = SampleEdgeRuntimeState(
                edge_id=row.edge_id,
                source_task_id=current_edge.source_task_id,
                target_task_id=current_edge.target_task_id,
                status=row.status,
                edge_snapshot_json=dict(row.edge_snapshot_json or current_edge.edge_snapshot_json),
            )

    def _apply_worker(self, row: SampleWorkerEventRow) -> None:
        task_id = row.task_id
        if task_id is None:
            return
        if row.event_type == "worker.removed":
            self.workers.pop(task_id, None)
            return
        self.workers[task_id] = SampleWorkerRuntimeState(
            task_id=task_id,
            worker_slug=row.worker_slug,
            worker_snapshot_json=dict(row.worker_snapshot_json),
        )

    def _apply_evaluator(self, row: SampleEvaluatorEventRow) -> None:
        task_id = row.task_id
        if task_id is None:
            return
        if row.event_type == "evaluator.removed":
            self._remove_evaluator(row)
            return
        self.evaluators_by_task_id.setdefault(task_id, []).append(
            SampleEvaluatorRuntimeState(
                task_id=task_id,
                evaluator_slug=row.evaluator_slug,
                evaluator_snapshot_json=dict(row.evaluator_snapshot_json),
            )
        )

    def _remove_evaluator(self, row: SampleEvaluatorEventRow) -> None:
        task_id = row.task_id
        if task_id is None:
            return
        if row.evaluator_slug:
            self.evaluators_by_task_id[task_id] = [
                evaluator
                for evaluator in self.evaluators_by_task_id.get(task_id, [])
                if evaluator.evaluator_slug != row.evaluator_slug
            ]
        else:
            self.evaluators_by_task_id.pop(task_id, None)

    def _apply_sandbox(self, row: SampleSandboxEventRow) -> None:
        task_id = row.task_id
        if task_id is None:
            return
        if row.event_type == "sandbox.removed":
            self.sandboxes.pop(task_id, None)
            return
        self.sandboxes[task_id] = SampleSandboxRuntimeState(
            task_id=task_id,
            sandbox_slug=row.sandbox_slug,
            sandbox_snapshot_json=dict(row.sandbox_snapshot_json),
        )

    def _apply_annotation(self, row: SampleAnnotationEventRow) -> None:
        target_key = (row.target_type, row.target_id, row.key)
        if row.event_type == "annotation.deleted":
            self.annotations.pop(target_key, None)
            return
        self.annotations[target_key] = SampleAnnotationRuntimeState(
            target_type=row.target_type,
            target_id=row.target_id,
            key=row.key,
            payload_json=dict(row.payload_json),
        )

    def to_state(self) -> SampleRuntimeState:
        return SampleRuntimeState(
            status=self.status,
            tasks=self.tasks,
            edges=self.edges,
            workers=self.workers,
            evaluators_by_task_id=self.evaluators_by_task_id,
            sandboxes=self.sandboxes,
            annotations=self.annotations,
        )


def _task_slug_from_event(
    row: SampleTaskEventRow,
    current: SampleTaskRuntimeState | None,
) -> str | None:
    if row.task_slug is not None:
        return row.task_slug
    if current is not None:
        return current.task_slug
    return None


def reconstruct_sample_runtime_state_at(
    session: Session,
    *,
    sample_id: UUID,
    at: datetime | None = None,
) -> SampleRuntimeState:
    rows: list[SampleRuntimeEventRow] = []
    for model in (
        SampleStatusEventRow,
        SampleTaskEventRow,
        SampleEdgeEventRow,
        SampleWorkerEventRow,
        SampleEvaluatorEventRow,
        SampleSandboxEventRow,
        SampleAnnotationEventRow,
    ):
        stmt = select(model).where(model.sample_id == sample_id)
        if at is not None:
            stmt = stmt.where(model.event_timestamp <= at)
        rows.extend(session.exec(stmt).all())
    rows.sort(key=lambda row: (row.event_timestamp, row.id))
    return SampleRuntimeState.from_events(rows)
