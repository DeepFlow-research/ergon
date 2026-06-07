"""Stable test-support reads for e2e smoke assertions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
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
