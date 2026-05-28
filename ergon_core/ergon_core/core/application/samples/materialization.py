"""Materialize authored Samples into typed runtime WAL and graph projections."""

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlmodel import Session

from pydantic import JsonValue

from ergon_core.core.application.runtime import status as graph_status
from ergon_core.core.application.samples.events import (
    SampleRuntimeEventAppender,
    append_sample_status_changed,
)
from ergon_core.core.persistence.graph.models import SampleGraphEdge, SampleGraphNode
from ergon_core.core.persistence.samples.models import (
    SampleEdgeEventRow,
    SampleEvaluatorEventRow,
    SampleSandboxEventRow,
    SampleTaskEventRow,
    SampleWorkerEventRow,
)
from ergon_core.core.persistence.shared.enums import SampleStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord

if TYPE_CHECKING:
    from ergon_core.api.experiment.sample import Sample


def materialize_sample(
    session: Session,
    *,
    sample: "Sample",
    sample_row: SampleRecord,
) -> None:
    wal = SampleRuntimeEventAppender(session)
    append_sample_status_changed(
        session,
        sample_id=sample_row.id,
        status=SampleStatus.PENDING,
        payload={"reason": "materialized"},
        actor="system:materialization",
    )

    task_ids_by_key: dict[str, UUID] = {}
    for task in sample.tasks:
        task_id = uuid4()
        task_ids_by_key[task.task_slug] = task_id
        task_json = task.model_dump(mode="json")
        worker_snapshot = task.worker.model_dump(mode="json")
        sandbox_snapshot = task.sandbox.model_dump(mode="json")
        worker_slug = task.worker.type_slug
        sandbox_type = _snapshot_type(
            sandbox_snapshot,
            fallback=_component_type_path(task.sandbox),
        )
        sandbox_slug = _component_display_slug(sandbox_type)

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
        wal.append_task_event(
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
                worker_type=_snapshot_type(worker_snapshot, fallback=task.worker.type_slug),
                model_target=task.worker.model,
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
                sandbox_type=sandbox_type,
                sandbox_snapshot_json=sandbox_snapshot,
                payload_json={"task_id": str(task_id), "sandbox": sandbox_snapshot},
                actor="system:materialization",
            )
        )
        for evaluator in task.evaluators:
            evaluator_snapshot = evaluator.model_dump(mode="json")
            evaluator_slug = evaluator.name
            wal.append_evaluator_event(
                SampleEvaluatorEventRow(
                    sample_id=sample_row.id,
                    task_id=task_id,
                    event_type="evaluator.added",
                    evaluator_slug=evaluator_slug,
                    evaluator_type=_snapshot_type(
                        evaluator_snapshot,
                        fallback=evaluator_slug,
                    ),
                    evaluator_snapshot_json=evaluator_snapshot,
                    payload_json={"task_id": str(task_id), "evaluator": evaluator_snapshot},
                    actor="system:materialization",
                )
            )

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


def _component_display_slug(type_path: str) -> str:
    return type_path.rsplit(":", 1)[-1].rsplit(".", 1)[-1]


def _component_type_path(component: object) -> str:
    cls = component.__class__
    return f"{cls.__module__}:{cls.__qualname__}"


def _snapshot_type(snapshot: dict[str, JsonValue], *, fallback: str) -> str:
    value = snapshot.get("_type")
    return str(value) if value else fallback
