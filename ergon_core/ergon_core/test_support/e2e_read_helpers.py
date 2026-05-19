"""Stable test-support reads for e2e smoke assertions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import (
    RunResource,
    RunTaskEvaluation,
    RunTaskExecution,
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


def _resource_snapshot(row: RunResource) -> ResourceSnapshot:
    return ResourceSnapshot(
        name=row.name,
        file_path=row.file_path,
        content_hash=row.content_hash,
        kind=row.kind,
        created_at=row.created_at,
    )


def _execution_snapshot(row: RunTaskExecution) -> TaskExecutionSnapshot:
    return TaskExecutionSnapshot(
        task_id=row.task_id,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def _evaluation_snapshot(row: RunTaskEvaluation) -> TaskEvaluationSnapshot:
    return TaskEvaluationSnapshot(score=row.score, created_at=row.created_at)


def read_resource_bytes(resource: ResourceSnapshot) -> bytes:
    return Path(resource.file_path).read_bytes()


def first_probe_resource(run_id: UUID) -> ResourceSnapshot | None:
    with get_session() as session:
        row = session.exec(
            select(RunResource)
            .where(RunResource.run_id == run_id)
            .where(
                RunResource.name.like("probe_%.json"),  # ty: ignore[unresolved-attribute]
            )
            .where(RunResource.kind == "report")
            .order_by(
                RunResource.created_at,  # ty: ignore[unresolved-attribute]
            )
            .limit(1),
        ).first()
    return None if row is None else _resource_snapshot(row)


def list_named_resources(
    run_id: UUID,
    *,
    prefix: str,
    suffix: str,
) -> list[ResourceSnapshot]:
    with get_session() as session:
        rows = list(
            session.exec(
                select(RunResource)
                .where(RunResource.run_id == run_id)
                .where(
                    RunResource.name.like(f"{prefix}%{suffix}"),  # ty: ignore[unresolved-attribute]
                ),
            ).all(),
        )
    return [_resource_snapshot(row) for row in rows]


def list_root_execution_and_evaluations(
    run_id: UUID,
) -> tuple[TaskExecutionSnapshot | None, list[TaskEvaluationSnapshot]]:
    with get_session() as session:
        root = session.exec(
            select(RunGraphNode)
            .where(RunGraphNode.run_id == run_id)
            .where(RunGraphNode.level == 0),
        ).one()
        execution = session.exec(
            select(RunTaskExecution).where(RunTaskExecution.task_id == root.task_id),
        ).first()
        evaluations = list(
            session.exec(
                select(RunTaskEvaluation)
                .where(RunTaskEvaluation.run_id == run_id)
                .where(RunTaskEvaluation.task_id == root.task_id),
            ).all(),
        )
    execution_snapshot = None if execution is None else _execution_snapshot(execution)
    return execution_snapshot, [_evaluation_snapshot(row) for row in evaluations]


def list_sandbox_command_wal(run_id: UUID) -> list[SandboxCommandWalSnapshot]:
    with get_session() as session:
        rows = list(
            session.exec(
                select(SandboxCommandWalEntry).where(SandboxCommandWalEntry.run_id == run_id),
            ).all(),
        )
    return [SandboxCommandWalSnapshot(command=row.command) for row in rows]


def list_sandbox_events(run_id: UUID) -> list[SandboxEventSnapshot]:
    with get_session() as session:
        rows = list(session.exec(select(SandboxEvent).where(SandboxEvent.run_id == run_id)).all())
    return [SandboxEventSnapshot(sandbox_id=row.sandbox_id, kind=row.kind) for row in rows]


def leaf_execution_timings_by_slug(run_id: UUID) -> dict[str, TaskExecutionSnapshot | None]:
    with get_session() as session:
        leaves = list(
            session.exec(
                select(RunGraphNode)
                .where(RunGraphNode.run_id == run_id)
                .where(RunGraphNode.level > 0),
            ).all(),
        )
        executions = list(
            session.exec(
                select(RunTaskExecution)
                .where(RunTaskExecution.run_id == run_id)
                .where(
                    RunTaskExecution.task_id.in_([leaf.task_id for leaf in leaves]),  # ty: ignore[unresolved-attribute]
                ),
            ).all(),
        )

    by_task = {execution.task_id: _execution_snapshot(execution) for execution in executions}
    return {leaf.task_slug: by_task.get(leaf.task_id) for leaf in leaves}
