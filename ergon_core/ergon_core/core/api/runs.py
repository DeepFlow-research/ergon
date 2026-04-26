"""FastAPI router for persisted run-detail snapshots."""

from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

from ergon_core.core.api.schemas import (
    RunCommunicationMessageDto,
    RunCommunicationThreadDto,
    RunContextEventDto,
    RunEvaluationCriterionDto,
    RunExecutionAttemptDto,
    RunGraphMutationDto,
    RunResourceDto,
    RunSandboxCommandDto,
    RunSandboxDto,
    RunSnapshotDto,
    RunTaskDto,
    RunTaskEvaluationDto,
    TrainingCurvePointDto,
    TrainingMetricDto,
    TrainingSessionDto,
)
from ergon_core.core.persistence.context.models import RunContextEvent
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionWorker,
)
from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunTaskEvaluation,
    RunTaskExecution,
    Thread,
    ThreadMessage,
    TrainingMetric,
    TrainingSession,
)
from ergon_core.core.runtime.services.run_read_service import RunReadService
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

router = APIRouter(prefix="/runs", tags=["runs"])


# ---------------------------------------------------------------------------
# Task tree helpers
# ---------------------------------------------------------------------------


def _build_task_map(
    nodes: list[RunGraphNode],
    edges: list[RunGraphEdge],
    worker_by_binding: dict[str, ExperimentDefinitionWorker],
    task_timestamps: dict[UUID, tuple[datetime | None, datetime | None]],
) -> tuple[dict[str, RunTaskDto], str, int, int, int, int, int, int]:
    """Three clean passes using stored containment columns.

    Pass 1: node columns (parent_node_id, level) — no edge traversal.
    Pass 2: reverse lookup for child_ids and is_leaf.
    Pass 3: dependency edges -> depends_on_ids.
    """
    if not nodes:
        return {}, "", 0, 0, 0, 0, 0, 0

    task_map: dict[str, RunTaskDto] = {}

    # Pass 1: build every node DTO from stored columns
    for node in nodes:
        nid = str(node.id)
        worker = (
            worker_by_binding.get(node.assigned_worker_slug)
            if node.assigned_worker_slug is not None
            else None
        )
        started_at, completed_at = task_timestamps.get(node.id, (None, None))
        task_map[nid] = RunTaskDto(
            id=nid,
            name=node.task_slug,
            description=node.description,
            status=node.status,
            parent_id=str(node.parent_node_id) if node.parent_node_id else None,
            child_ids=[],
            depends_on_ids=[],
            is_leaf=True,
            level=node.level,
            assigned_worker_id=str(worker.id) if worker else None,
            assigned_worker_name=node.assigned_worker_slug,
            started_at=started_at,
            completed_at=completed_at,
        )

    # Pass 2: derive child_ids and is_leaf from parent_id
    for nid, dto in task_map.items():
        if dto.parent_id and dto.parent_id in task_map:
            parent = task_map[dto.parent_id]
            task_map[dto.parent_id] = parent.model_copy(
                update={"child_ids": [*parent.child_ids, nid], "is_leaf": False}
            )

    # Pass 3: dependency edges -> depends_on_ids
    for edge in edges:
        src, tgt = str(edge.source_node_id), str(edge.target_node_id)
        target_task = task_map.get(tgt)
        if target_task is None:
            continue
        task_map[tgt] = target_task.model_copy(
            update={"depends_on_ids": [*target_task.depends_on_ids, src]}
        )

    root_id = next((t.id for t in task_map.values() if t.parent_id is None), "")
    total = len(task_map)
    leaves = [t for t in task_map.values() if t.is_leaf]
    total_leaf = len(leaves)
    completed = sum(1 for t in leaves if t.status == "completed")
    failed = sum(1 for t in leaves if t.status == "failed")
    running = sum(1 for t in leaves if t.status == "running")
    cancelled = sum(1 for t in leaves if t.status == "cancelled")

    return task_map, root_id, total, total_leaf, completed, failed, running, cancelled


# ---------------------------------------------------------------------------
# Per-task keyed helpers
# ---------------------------------------------------------------------------


def _task_keyed_executions(
    executions: list[RunTaskExecution],
    worker_map: dict[UUID, ExperimentDefinitionWorker],
) -> dict[str, list[RunExecutionAttemptDto]]:
    by_task: dict[str, list[RunExecutionAttemptDto]] = defaultdict(list)
    for ex in sorted(
        executions,
        key=lambda e: ("" if e.node_id is None else str(e.node_id), e.attempt_number),
    ):
        if ex.node_id is None:
            continue
        tid = str(ex.node_id)
        error_msg: str | None = None
        if ex.error_json:
            message = ex.error_json.get("message")
            error_msg = message if isinstance(message, str) else str(ex.error_json)

        worker = worker_map.get(ex.definition_worker_id) if ex.definition_worker_id else None
        agent_id = str(worker.id) if worker else None
        agent_name = worker.binding_key if worker else None

        resource_ids: list[str] = []
        output = ex.parsed_output()
        if "resource_ids" in output:
            resource_ids = [str(r) for r in output["resource_ids"]]

        by_task[tid].append(
            RunExecutionAttemptDto(
                id=str(ex.id),
                task_id=tid,
                attempt_number=ex.attempt_number,
                status=ex.status,
                started_at=ex.started_at,
                completed_at=ex.completed_at,
                final_assistant_message=ex.final_assistant_message,
                error_message=error_msg,
                score=None,
                agent_id=agent_id,
                agent_name=agent_name,
                output_resource_ids=resource_ids,
            )
        )
    return dict(by_task)


def _task_keyed_resources(
    resources: list[RunResource],
    execution_task_map: dict[UUID, UUID],
) -> dict[str, list[RunResourceDto]]:
    by_task: dict[str, list[RunResourceDto]] = defaultdict(list)
    for r in resources:
        task_id_uuid = execution_task_map.get(r.task_execution_id) if r.task_execution_id else None
        if task_id_uuid is None:
            continue
        tid = str(task_id_uuid)
        by_task[tid].append(
            RunResourceDto(
                id=str(r.id),
                task_id=tid,
                task_execution_id=str(r.task_execution_id) if r.task_execution_id else "",
                name=r.name,
                mime_type=r.mime_type,
                file_path=r.file_path,
                size_bytes=r.size_bytes,
                created_at=r.created_at,
            )
        )
    return dict(by_task)


def _task_keyed_evaluations(
    evaluations: list[RunTaskEvaluation],
    run_id: str,
    defn_to_node: dict[UUID, UUID],
) -> dict[str, RunTaskEvaluationDto]:
    result: dict[str, RunTaskEvaluationDto] = {}
    for ev in evaluations:
        node_id = ev.node_id
        if node_id is None:
            # Evaluation rows without runtime node identity cannot be
            # truthfully rendered in a task workspace.
            continue
        tid = str(node_id)
        summary = ev.parsed_summary()

        criterion_results = [
            RunEvaluationCriterionDto(
                id=f"{ev.id}-{i}",
                stage_num=cr.stage_num,
                stage_name=cr.stage_name,
                criterion_num=cr.criterion_num,
                criterion_type=cr.criterion_type,
                criterion_description=cr.criterion_description,
                evaluation_input=cr.evaluation_input,
                score=cr.score,
                max_score=cr.max_score,
                feedback=cr.feedback,
                evaluated_action_ids=cr.evaluated_action_ids,
                evaluated_resource_ids=cr.evaluated_resource_ids,
                error=cr.error,
            )
            for i, cr in enumerate(summary.criterion_results)
        ]

        result[tid] = RunTaskEvaluationDto(
            id=str(ev.id),
            run_id=run_id,
            task_id=tid,
            total_score=0.0 if ev.score is None else ev.score,
            max_score=summary.max_score,
            normalized_score=summary.normalized_score,
            stages_evaluated=summary.stages_evaluated,
            stages_passed=summary.stages_passed,
            failed_gate=summary.failed_gate,
            created_at=ev.created_at,
            criterion_results=criterion_results,
        )
    return result


def _task_keyed_sandboxes(
    run_summary: dict,
) -> dict[str, RunSandboxDto]:
    """Extract sandbox info from run summary_json if available."""
    result: dict[str, RunSandboxDto] = {}
    sandboxes = run_summary.get("sandboxes", {})
    for task_id, sb in sandboxes.items():
        commands = [
            RunSandboxCommandDto(
                command=cmd.get("command", ""),
                stdout=cmd.get("stdout"),
                stderr=cmd.get("stderr"),
                exit_code=cmd.get("exit_code"),
                duration_ms=cmd.get("duration_ms"),
                timestamp=cmd.get("timestamp", "1970-01-01T00:00:00Z"),
            )
            for cmd in sb.get("commands", [])
        ]
        result[task_id] = RunSandboxDto(
            sandbox_id=sb.get("sandbox_id", ""),
            task_id=task_id,
            template=sb.get("template"),
            timeout_minutes=sb.get("timeout_minutes", 5),
            status=sb.get("status", "unknown"),
            created_at=sb.get("created_at", "1970-01-01T00:00:00Z"),
            closed_at=sb.get("closed_at"),
            close_reason=sb.get("close_reason"),
            commands=commands,
        )
    return result


# ---------------------------------------------------------------------------
# Current task statuses from state events
# ---------------------------------------------------------------------------


def _build_communication_threads(
    threads: list[Thread],
    messages: list[ThreadMessage],
    execution_task_map: dict[UUID, UUID],
) -> list[RunCommunicationThreadDto]:
    msgs_by_thread: dict[UUID, list[ThreadMessage]] = defaultdict(list)
    for m in sorted(messages, key=lambda m: m.sequence_num):
        msgs_by_thread[m.thread_id].append(m)

    result: list[RunCommunicationThreadDto] = []
    for t in threads:
        thread_messages = msgs_by_thread.get(t.id, [])
        task_ids = {
            task_id
            for message in thread_messages
            if message.task_execution_id is not None
            for task_id in [execution_task_map.get(message.task_execution_id)]
            if task_id is not None
        }
        thread_task_id = next(iter(task_ids)) if len(task_ids) == 1 else None
        result.append(
            RunCommunicationThreadDto(
                id=str(t.id),
                run_id=str(t.run_id),
                task_id=str(thread_task_id) if thread_task_id else None,
                topic=t.topic,
                summary=t.summary,
                agent_a_id=t.agent_a_id,
                agent_b_id=t.agent_b_id,
                created_at=t.created_at,
                updated_at=t.updated_at,
                messages=[
                    RunCommunicationMessageDto(
                        id=str(m.id),
                        thread_id=str(m.thread_id),
                        run_id=str(m.run_id),
                        thread_topic=t.topic,
                        task_id=(
                            str(execution_task_map[m.task_execution_id])
                            if m.task_execution_id
                            and m.task_execution_id in execution_task_map
                            else None
                        ),
                        task_execution_id=str(m.task_execution_id) if m.task_execution_id else None,
                        from_agent_id=m.from_agent_id,
                        to_agent_id=m.to_agent_id,
                        content=m.content,
                        sequence_num=m.sequence_num,
                        created_at=m.created_at,
                    )
                    for m in thread_messages
                ],
            )
        )
    return result


def _task_timestamps(
    executions: list[RunTaskExecution],
) -> dict[UUID, tuple[datetime | None, datetime | None]]:
    """Derive per-task started_at/completed_at from execution records."""
    result: dict[UUID, tuple[datetime | None, datetime | None]] = {}
    by_task: dict[UUID, list[RunTaskExecution]] = defaultdict(list)
    for ex in executions:
        if ex.node_id is not None:
            by_task[ex.node_id].append(ex)

    for task_id, execs in by_task.items():
        started = min((e.started_at for e in execs if e.started_at), default=None)
        completed = max((e.completed_at for e in execs if e.completed_at), default=None)
        result[task_id] = (started, completed)
    return result


def _context_events_by_task(
    context_events_rows: list[RunContextEvent],
    execution_task_map: dict[UUID, UUID],
) -> dict[str, list[RunContextEventDto]]:
    context_events_by_task: dict[str, list[RunContextEventDto]] = defaultdict(list)
    for event in context_events_rows:
        task_node_id = execution_task_map.get(event.task_execution_id)
        if task_node_id is None:
            continue
        context_events_by_task[str(task_node_id)].append(
            RunContextEventDto(
                id=str(event.id),
                task_execution_id=str(event.task_execution_id),
                task_node_id=str(task_node_id),
                worker_binding_key=event.worker_binding_key,
                sequence=event.sequence,
                event_type=event.event_type,
                payload=event.payload,
                created_at=event.created_at.isoformat(),
                started_at=event.started_at.isoformat() if event.started_at else None,
                completed_at=event.completed_at.isoformat() if event.completed_at else None,
            )
        )
    return dict(context_events_by_task)


# ---------------------------------------------------------------------------
# Snapshot builder
# ---------------------------------------------------------------------------


def build_run_snapshot(run_id: UUID) -> RunSnapshotDto | None:
    return RunReadService().build_run_snapshot(run_id)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/{run_id}", response_model=RunSnapshotDto)
def get_run(run_id: UUID) -> RunSnapshotDto:
    """Get a persisted run-detail snapshot suitable for frontend hydration."""
    snapshot = build_run_snapshot(run_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return snapshot


# ---------------------------------------------------------------------------
# Mutations endpoint (Timeline scrubber)
# ---------------------------------------------------------------------------


@router.get("/{run_id}/mutations", response_model=list[RunGraphMutationDto])
def get_mutations(run_id: UUID) -> list[RunGraphMutationDto]:
    """Return the append-only mutation log for a run, ordered by sequence.

    Used by the Timeline scrubber to replay DAG state at any point in time.
    """
    mutations = RunReadService().list_mutations(run_id)
    if mutations is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return mutations


# ---------------------------------------------------------------------------
# Resource content endpoint (file viewer modal)
# ---------------------------------------------------------------------------


# Max bytes we'll stream from a RunResource. The modal viewer is not a
# download manager — anything bigger 413s so the browser doesn't OOM.
_RESOURCE_CONTENT_MAX_BYTES: int = 10 * 1024 * 1024


@router.get("/{run_id}/resources/{resource_id}/content")
def get_resource_content(run_id: UUID, resource_id: UUID) -> FileResponse:
    """Stream the blob bytes for a RunResource.

    Used by the dashboard's file-viewer modal. Enforces:
    - resource must belong to the named run (no cross-run leaks);
    - resolved path must sit under ``ERGON_BLOB_ROOT`` (traversal guard);
    - size <= ``_RESOURCE_CONTENT_MAX_BYTES`` (413 otherwise).
    """
    try:
        blob = RunReadService().get_resource_blob(run_id, resource_id)
    except (FileNotFoundError, OSError) as e:
        raise HTTPException(status_code=404, detail="Resource blob missing on disk") from e
    except ValueError as e:
        message = str(e)
        if message.startswith("resource-too-large:"):
            size = int(message.removeprefix("resource-too-large:"))
            raise HTTPException(
                status_code=413,
                detail=f"Resource content {size} bytes exceeds viewer limit "
                f"({_RESOURCE_CONTENT_MAX_BYTES} bytes)",
            ) from e
        raise HTTPException(status_code=404, detail="Resource blob outside blob root") from e

    if blob is None:
        raise HTTPException(status_code=404, detail=f"Resource {resource_id} not found")

    return FileResponse(
        path=blob.path,
        media_type=blob.media_type,
        filename=blob.filename,
        content_disposition_type="inline",
    )


# ---------------------------------------------------------------------------
# Training curves endpoint (RL observability)
# ---------------------------------------------------------------------------


@router.get("/training/curves", response_model=list[TrainingCurvePointDto])
def get_training_curves(
    definition_id: UUID | None = None,
    cohort_id: UUID | None = None,
) -> list[TrainingCurvePointDto]:
    """Return score-over-step data for checkpoint evaluations.

    Reads ``summary_json`` on ``RunRecord`` for checkpoint metadata
    (``checkpoint_step``, ``checkpoint_path``) written by the eval
    watcher, and aggregates ``RunTaskEvaluation.score`` per run.

    Filter by ``definition_id`` or ``cohort_id``.
    """
    return RunReadService().list_training_curves(
        definition_id=definition_id,
        cohort_id=cohort_id,
    )


# ---------------------------------------------------------------------------
# Training sessions endpoints
# ---------------------------------------------------------------------------


@router.get("/training/sessions", response_model=list[TrainingSessionDto])
def get_training_sessions(
    definition_id: UUID | None = None,
) -> list[TrainingSessionDto]:
    """List training sessions, optionally filtered by definition."""
    return RunReadService().list_training_sessions(definition_id=definition_id)


@router.get("/training/sessions/{session_id}/metrics", response_model=list[TrainingMetricDto])
def get_training_metrics(session_id: UUID) -> list[TrainingMetricDto]:
    """Get per-step training metrics for a session."""
    return RunReadService().list_training_metrics(session_id)
