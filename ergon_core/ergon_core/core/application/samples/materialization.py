"""Materialize authored Samples into typed runtime WAL and graph projections."""

from collections.abc import Mapping
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlmodel import Session

from ergon_core.api.experiment.sample import Sample
from ergon_core.core.application.runtime import status as graph_status
from ergon_core.core.application.samples.events import SampleRuntimeEventAppender
from ergon_core.core.persistence.graph.models import SampleGraphEdge, SampleGraphNode
from ergon_core.core.persistence.samples.models import (
    SampleEdgeEventRow,
    SampleEvaluatorEventRow,
    SampleSandboxEventRow,
    SampleStatusEventRow,
    SampleTaskEventRow,
    SampleWorkerEventRow,
)
from ergon_core.core.persistence.shared.enums import SampleStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord


def component_slug(snapshot: Mapping[str, JsonValue], *, fallback: str) -> str:
    value = snapshot.get("type_slug") or snapshot.get("slug") or snapshot.get("name")
    if isinstance(value, str) and value:
        return value
    component_type = component_type_path(snapshot, fallback=fallback)
    return component_type.rsplit(":", 1)[-1].rsplit(".", 1)[-1]


def component_type_path(snapshot: Mapping[str, JsonValue], *, fallback: str) -> str:
    value = snapshot.get("_type") or snapshot.get("type")
    return value if isinstance(value, str) and value else fallback


def component_model_target(snapshot: Mapping[str, JsonValue]) -> str | None:
    value = snapshot.get("model") or snapshot.get("model_target")
    return value if isinstance(value, str) else None


def materialize_sample(
    session: Session,
    *,
    sample: Sample,
    sample_row: SampleRecord,
) -> None:
    wal = SampleRuntimeEventAppender(session)
    wal.append_status_event(
        SampleStatusEventRow(
            sample_id=sample_row.id,
            event_type="sample.status_changed",
            status=SampleStatus.PENDING,
            payload_json={"reason": "materialized"},
            actor="system:materialization",
        )
    )

    task_ids_by_key: dict[str, UUID] = {}
    for task in sample.tasks:
        task_id = uuid4()
        task_ids_by_key[task.task_slug] = task_id
        task_json = task.model_dump(mode="json")
        worker_snapshot = _required_component_snapshot(task_json, "worker")
        sandbox_snapshot = _required_component_snapshot(task_json, "sandbox")
        worker_slug = component_slug(worker_snapshot, fallback="worker")
        sandbox_slug = component_slug(sandbox_snapshot, fallback="sandbox")

        session.add(
            SampleGraphNode(
                sample_id=sample_row.id,
                task_id=task_id,
                instance_key=task.instance_key,
                task_slug=task.task_slug,
                description=task.description,
                task_json=task_json,
                is_dynamic=False,
                status=graph_status.PENDING,
                assigned_worker_slug=worker_slug,
            )
        )
        task_event = wal.append_task_event(
            SampleTaskEventRow(
                sample_id=sample_row.id,
                task_id=task_id,
                event_type="task.added",
                task_slug=task.task_slug,
                status=graph_status.PENDING,
                task_snapshot_json=task_json,
                payload_json={
                    "task_id": str(task_id),
                    "task_slug": task.task_slug,
                    "worker_slug": worker_slug,
                    "sandbox_slug": sandbox_slug,
                },
                actor="system:materialization",
            )
        )
        wal.append_worker_event(
            SampleWorkerEventRow(
                sample_id=sample_row.id,
                task_id=task_id,
                event_type="worker.added",
                worker_slug=worker_slug,
                worker_type=component_type_path(worker_snapshot, fallback=worker_slug),
                model_target=component_model_target(worker_snapshot),
                worker_snapshot_json=worker_snapshot,
                payload_json={"task_id": str(task_id), "worker": worker_snapshot},
                actor="system:materialization",
            )
        )
        wal.append_sandbox_event(
            SampleSandboxEventRow(
                sample_id=sample_row.id,
                task_id=task_id,
                event_type="sandbox.added",
                sandbox_slug=sandbox_slug,
                sandbox_type=component_type_path(sandbox_snapshot, fallback=sandbox_slug),
                sandbox_snapshot_json=sandbox_snapshot,
                payload_json={"task_id": str(task_id), "sandbox": sandbox_snapshot},
                actor="system:materialization",
            )
        )
        for evaluator_snapshot in _evaluator_snapshots(task_json):
            evaluator_slug = component_slug(evaluator_snapshot, fallback="default")
            wal.append_evaluator_event(
                SampleEvaluatorEventRow(
                    sample_id=sample_row.id,
                    task_id=task_id,
                    event_type="evaluator.added",
                    evaluator_slug=evaluator_slug,
                    evaluator_type=component_type_path(evaluator_snapshot, fallback=evaluator_slug),
                    evaluator_snapshot_json=evaluator_snapshot,
                    payload_json={"task_id": str(task_id), "evaluator": evaluator_snapshot},
                    actor="system:materialization",
                )
            )
        session.add(task_event)

    session.flush()
    for task in sample.tasks:
        target_task_id = task_ids_by_key[task.task_slug]
        for dependency_key in task.dependency_task_slugs:
            source_task_id = task_ids_by_key[dependency_key]
            edge = SampleGraphEdge(
                sample_id=sample_row.id,
                source_task_id=source_task_id,
                target_task_id=target_task_id,
                status=graph_status.EDGE_PENDING,
            )
            session.add(edge)
            session.flush()
            wal.append_edge_event(
                SampleEdgeEventRow(
                    sample_id=sample_row.id,
                    edge_id=edge.id,
                    event_type="edge.added",
                    source_task_id=source_task_id,
                    target_task_id=target_task_id,
                    status=graph_status.EDGE_PENDING,
                    edge_snapshot_json={
                        "source_task_slug": dependency_key,
                        "target_task_slug": task.task_slug,
                    },
                    payload_json={
                        "source_task_id": str(source_task_id),
                        "target_task_id": str(target_task_id),
                        "source_task_slug": dependency_key,
                        "target_task_slug": task.task_slug,
                    },
                    actor="system:materialization",
                )
            )
    session.flush()


def _required_component_snapshot(task_json: Mapping[str, JsonValue], key: str) -> dict:
    value = task_json.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Task snapshot is missing object-bound {key}")
    return value


def _evaluator_snapshots(task_json: Mapping[str, JsonValue]) -> list[dict]:
    evaluators = task_json.get("evaluators", [])
    if not isinstance(evaluators, list):
        return []
    return [snapshot for snapshot in evaluators if isinstance(snapshot, dict)]
