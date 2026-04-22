"""FastAPI router for persisted run-detail snapshots."""

import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any
from uuid import UUID

from ergon_core.core.api.schemas import (
    RunCommunicationMessageDto,
    RunCommunicationThreadDto,
    RunContextEventDto,
    RunEvaluationCriterionDto,
    RunExecutionAttemptDto,
    RunGenerationTurnDto,
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
    RunGenerationTurn,
    RunRecord,
    RunResource,
    RunTaskEvaluation,
    RunTaskExecution,
    Thread,
    ThreadMessage,
    TrainingMetric,
    TrainingSession,
)
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
        worker = worker_by_binding.get(node.assigned_worker_slug or "")
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
    for ex in sorted(executions, key=lambda e: (str(e.node_id or ""), e.attempt_number)):
        if ex.node_id is None:
            continue
        tid = str(ex.node_id)
        error_msg: str | None = None
        if ex.error_json:
            error_msg = ex.error_json.get("message") or str(ex.error_json)

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
        node_id = defn_to_node.get(ev.definition_task_id)
        if node_id is None:
            # Dynamic nodes have no definition_task_id; evaluations for unknown tasks are skipped.
            # When dynamic-task evaluation is added, RunTaskEvaluation will need a node_id
            # foreign key so evaluations can be mapped without going through the definition layer.
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
            total_score=ev.score or 0.0,
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
) -> list[RunCommunicationThreadDto]:
    msgs_by_thread: dict[UUID, list[ThreadMessage]] = defaultdict(list)
    for m in sorted(messages, key=lambda m: m.sequence_num):
        msgs_by_thread[m.thread_id].append(m)

    result: list[RunCommunicationThreadDto] = []
    for t in threads:
        result.append(
            RunCommunicationThreadDto(
                id=str(t.id),
                run_id=str(t.run_id),
                topic=t.topic,
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
                        from_agent_id=m.from_agent_id,
                        to_agent_id=m.to_agent_id,
                        content=m.content,
                        sequence_num=m.sequence_num,
                        created_at=m.created_at,
                    )
                    for m in msgs_by_thread.get(t.id, [])
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


# ---------------------------------------------------------------------------
# Snapshot builder
# ---------------------------------------------------------------------------


def build_run_snapshot(run_id: UUID, session: Session) -> RunSnapshotDto | None:
    run = session.get(RunRecord, run_id)
    if run is None:
        return None

    definition = session.get(ExperimentDefinition, run.experiment_definition_id)
    if definition is None:
        return None

    def_id = run.experiment_definition_id

    # Graph nodes and edges for this run
    nodes_stmt = select(RunGraphNode).where(RunGraphNode.run_id == run_id)
    nodes = list(session.exec(nodes_stmt).all())

    edges_stmt = select(RunGraphEdge).where(RunGraphEdge.run_id == run_id)
    edges = list(session.exec(edges_stmt).all())

    # Worker definitions for this experiment
    workers_stmt = select(ExperimentDefinitionWorker).where(
        ExperimentDefinitionWorker.experiment_definition_id == def_id
    )
    def_workers = list(session.exec(workers_stmt).all())
    worker_by_id: dict[UUID, ExperimentDefinitionWorker] = {w.id: w for w in def_workers}
    worker_by_binding: dict[str, ExperimentDefinitionWorker] = {
        w.binding_key: w for w in def_workers
    }

    # Run telemetry
    exec_stmt = select(RunTaskExecution).where(RunTaskExecution.run_id == run_id)
    executions = list(session.exec(exec_stmt).all())

    resources_stmt = select(RunResource).where(RunResource.run_id == run_id)
    resources = list(session.exec(resources_stmt).all())

    evals_stmt = select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)
    evaluations = list(session.exec(evals_stmt).all())

    threads_stmt = select(Thread).where(Thread.run_id == run_id)
    threads = list(session.exec(threads_stmt).all())

    thread_msgs_stmt = select(ThreadMessage).where(ThreadMessage.run_id == run_id)
    thread_messages = list(session.exec(thread_msgs_stmt).all())

    # Derived maps
    timestamps = _task_timestamps(executions)
    (
        task_map,
        root_task_id,
        total_tasks,
        total_leaf,
        completed_tasks,
        failed_tasks,
        running_tasks,
        cancelled_tasks,
    ) = _build_task_map(nodes, edges, worker_by_binding, timestamps)

    execution_task_map: dict[UUID, UUID] = {
        ex.id: ex.node_id for ex in executions if ex.node_id is not None
    }

    # One RunGraphNode per definition task (initialize_from_definition guarantees this).
    defn_to_node: dict[UUID, UUID] = {
        n.definition_task_id: n.id for n in nodes if n.definition_task_id is not None
    }

    # Generation turns
    gen_turns_stmt = (
        select(RunGenerationTurn)
        .where(RunGenerationTurn.run_id == run_id)
        .order_by(RunGenerationTurn.task_execution_id, RunGenerationTurn.turn_index)
    )
    gen_turns = list(session.exec(gen_turns_stmt).all())

    gen_turns_by_task: dict[str, list[RunGenerationTurnDto]] = defaultdict(list)
    for turn in gen_turns:
        node_uuid = execution_task_map.get(turn.task_execution_id)
        if node_uuid is None:
            continue
        gen_turns_by_task[str(node_uuid)].append(
            RunGenerationTurnDto(
                id=str(turn.id),
                task_execution_id=str(turn.task_execution_id),
                worker_binding_key=turn.worker_binding_key,
                turn_index=turn.turn_index,
                prompt_text=turn.prompt_text,
                raw_response=turn.raw_response,
                response_text=turn.response_text,
                tool_calls=turn.tool_calls_json,
                tool_results=turn.tool_results_json,
                policy_version=turn.policy_version,
                has_logprobs=turn.token_ids_json is not None,
                created_at=turn.created_at.isoformat() if turn.created_at else None,
            )
        )

    # Load context events
    context_events_stmt = (
        select(RunContextEvent)
        .where(RunContextEvent.run_id == run_id)
        .order_by(RunContextEvent.task_execution_id, RunContextEvent.sequence)
    )
    context_events_rows = list(session.exec(context_events_stmt).all())

    context_events_by_task: dict[str, list[RunContextEventDto]] = defaultdict(list)
    for event in context_events_rows:
        task_node_id = execution_task_map.get(event.task_execution_id)
        if task_node_id is None:
            continue
        context_events_by_task[str(task_node_id)].append(
            RunContextEventDto(
                id=str(event.id),
                task_execution_id=str(event.task_execution_id),
                sequence=event.sequence,
                event_type=event.event_type,
                payload=event.payload,
                created_at=event.created_at.isoformat(),
                started_at=event.started_at.isoformat() if event.started_at else None,
                completed_at=event.completed_at.isoformat() if event.completed_at else None,
            )
        )

    # Compute final score from evaluations
    final_score: float | None = None
    if evaluations:
        scores = [ev.score for ev in evaluations if ev.score is not None]
        if scores:
            final_score = sum(scores) / len(scores)

    # Duration
    duration_seconds: float | None = None
    if run.started_at and run.completed_at:
        duration_seconds = (run.completed_at - run.started_at).total_seconds()

    run_id_str = str(run.id)
    run_summary = run.parsed_summary()

    # Build run name from definition metadata
    meta = definition.parsed_metadata()
    run_name = str(meta.get("name", definition.benchmark_type))

    return RunSnapshotDto(
        id=run_id_str,
        experiment_id=str(def_id),
        name=run_name,
        status=run.status,
        tasks=task_map,
        root_task_id=root_task_id,
        resources_by_task=_task_keyed_resources(resources, execution_task_map),
        executions_by_task=_task_keyed_executions(executions, worker_by_id),
        evaluations_by_task=_task_keyed_evaluations(evaluations, run_id_str, defn_to_node),
        generation_turns_by_task=dict(gen_turns_by_task),
        context_events_by_task=dict(context_events_by_task),
        sandboxes_by_task=_task_keyed_sandboxes(run_summary),
        threads=_build_communication_threads(threads, thread_messages),
        started_at=run.started_at or run.created_at,
        completed_at=run.completed_at,
        duration_seconds=duration_seconds,
        total_tasks=total_tasks,
        total_leaf_tasks=total_leaf,
        completed_tasks=completed_tasks,
        failed_tasks=failed_tasks,
        running_tasks=running_tasks,
        cancelled_tasks=cancelled_tasks,
        final_score=final_score,
        error=run.error_message,
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/{run_id}", response_model=RunSnapshotDto)
def get_run(run_id: UUID) -> RunSnapshotDto:
    """Get a persisted run-detail snapshot suitable for frontend hydration."""
    with get_session() as session:
        snapshot = build_run_snapshot(run_id, session)
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
    with get_session() as session:
        run = session.get(RunRecord, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

        stmt = (
            select(RunGraphMutation)
            .where(RunGraphMutation.run_id == run_id)
            .order_by(RunGraphMutation.sequence)
        )
        mutations = list(session.exec(stmt).all())

    return [
        RunGraphMutationDto(
            id=str(m.id),
            run_id=str(m.run_id),
            sequence=m.sequence,
            mutation_type=m.mutation_type,
            target_type=m.target_type,
            target_id=str(m.target_id),
            actor=m.actor,
            old_value=m.old_value,
            new_value=m.new_value,
            reason=m.reason,
            created_at=m.created_at.isoformat(),
        )
        for m in mutations
    ]


# ---------------------------------------------------------------------------
# Generation turns endpoint (RL observability)
# ---------------------------------------------------------------------------


@router.get("/{run_id}/generations", response_model=list[RunGenerationTurnDto])
def get_generations(
    run_id: UUID,
    include: str | None = None,
) -> list[RunGenerationTurnDto]:
    """Get lossless generation turns for a run.

    Each turn contains the raw model request/response, extracted text,
    tool calls, tool results, and optionally logprobs.

    Query params:
        include: comma-separated fields to include.  ``logprobs`` adds
            ``token_ids`` and ``logprobs`` arrays (can be large).
    """
    include_logprobs = include is not None and "logprobs" in include.split(",")

    with get_session() as session:
        run = session.get(RunRecord, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

        stmt = (
            select(RunGenerationTurn)
            .where(RunGenerationTurn.run_id == run_id)
            .order_by(RunGenerationTurn.task_execution_id, RunGenerationTurn.turn_index)
        )
        turns = list(session.exec(stmt).all())

    result: list[RunGenerationTurnDto] = []
    for turn in turns:
        dto = RunGenerationTurnDto(
            id=str(turn.id),
            task_execution_id=str(turn.task_execution_id),
            worker_binding_key=turn.worker_binding_key,
            turn_index=turn.turn_index,
            prompt_text=turn.prompt_text,
            raw_response=turn.raw_response,
            response_text=turn.response_text,
            tool_calls=turn.tool_calls_json,
            tool_results=turn.tool_results_json,
            policy_version=turn.policy_version,
            has_logprobs=turn.token_ids_json is not None,
            created_at=turn.created_at.isoformat() if turn.created_at else None,
            token_ids=turn.token_ids_json if include_logprobs else None,
            logprobs=turn.logprobs_json if include_logprobs else None,
        )
        result.append(dto)

    return result


# ---------------------------------------------------------------------------
# Resource content endpoint (file viewer modal)
# ---------------------------------------------------------------------------


# Max bytes we'll stream from a RunResource. The modal viewer is not a
# download manager — anything bigger 413s so the browser doesn't OOM.
_RESOURCE_CONTENT_MAX_BYTES: int = 10 * 1024 * 1024


def _blob_root() -> Path:
    """Resolve the blob root used by publishers. Mirrors
    ``ergon_core.core.providers.sandbox.resource_publisher._DEFAULT_BLOB_ROOT``
    at call time so tests can override via ``ERGON_BLOB_ROOT``.
    """
    return Path(os.environ.get("ERGON_BLOB_ROOT", "/var/ergon/blob")).resolve()


@router.get("/{run_id}/resources/{resource_id}/content")
def get_resource_content(run_id: UUID, resource_id: UUID) -> FileResponse:
    """Stream the blob bytes for a RunResource.

    Used by the dashboard's file-viewer modal. Enforces:
    - resource must belong to the named run (no cross-run leaks);
    - resolved path must sit under ``ERGON_BLOB_ROOT`` (traversal guard);
    - size <= ``_RESOURCE_CONTENT_MAX_BYTES`` (413 otherwise).
    """
    with get_session() as session:
        stmt = select(RunResource).where(
            RunResource.id == resource_id,
            RunResource.run_id == run_id,
        )
        resource = session.exec(stmt).first()

    if resource is None:
        raise HTTPException(status_code=404, detail=f"Resource {resource_id} not found")

    if resource.file_path is None:
        raise HTTPException(status_code=404, detail="Resource has no backing blob")

    try:
        blob_path = Path(resource.file_path).resolve(strict=True)
    except (FileNotFoundError, OSError) as e:
        raise HTTPException(status_code=404, detail="Resource blob missing on disk") from e

    root = _blob_root()
    try:
        blob_path.relative_to(root)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Resource blob outside blob root") from e

    size = blob_path.stat().st_size
    if size > _RESOURCE_CONTENT_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Resource content {size} bytes exceeds viewer limit "
            f"({_RESOURCE_CONTENT_MAX_BYTES} bytes)",
        )

    media_type = resource.mime_type or "application/octet-stream"
    return FileResponse(
        path=blob_path,
        media_type=media_type,
        filename=resource.name,
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
    with get_session() as session:
        stmt = select(RunRecord)
        if definition_id:
            stmt = stmt.where(RunRecord.experiment_definition_id == definition_id)
        if cohort_id:
            stmt = stmt.where(RunRecord.cohort_id == cohort_id)
        stmt = stmt.order_by(RunRecord.created_at)
        runs = list(session.exec(stmt).all())

        all_run_ids = [r.id for r in runs]
        evals = list(
            session.exec(
                select(RunTaskEvaluation).where(RunTaskEvaluation.run_id.in_(all_run_ids))  # type: ignore[union-attr]
            ).all()
        )

    scores_by_run: dict[UUID, list[float]] = defaultdict(list)
    for ev in evals:
        if ev.score is not None:
            scores_by_run[ev.run_id].append(ev.score)

    points: list[TrainingCurvePointDto] = []
    for run in runs:
        summary: dict[str, Any] = run.summary_json or {}  # slopcop: ignore[no-typing-any]
        step = summary.get("checkpoint_step")
        if step is None:
            continue

        run_scores = scores_by_run.get(run.id, [])
        if not run_scores:
            continue

        points.append(
            TrainingCurvePointDto(
                run_id=str(run.id),
                step=int(step),
                mean_score=mean(run_scores),
                benchmark_type=summary.get("benchmark_type"),
                created_at=run.created_at.isoformat() if run.created_at else None,
            )
        )

    return points


# ---------------------------------------------------------------------------
# Training sessions endpoints
# ---------------------------------------------------------------------------


@router.get("/training/sessions", response_model=list[TrainingSessionDto])
def get_training_sessions(
    definition_id: UUID | None = None,
) -> list[TrainingSessionDto]:
    """List training sessions, optionally filtered by definition."""
    with get_session() as session:
        stmt = select(TrainingSession).order_by(TrainingSession.started_at.desc())
        if definition_id:
            stmt = stmt.where(TrainingSession.experiment_definition_id == definition_id)
        sessions = list(session.exec(stmt).all())

    return [
        TrainingSessionDto(
            id=str(s.id),
            experiment_definition_id=str(s.experiment_definition_id),
            model_name=s.model_name,
            status=s.status,
            started_at=s.started_at.isoformat() if s.started_at else None,
            completed_at=s.completed_at.isoformat() if s.completed_at else None,
            output_dir=s.output_dir,
            total_steps=s.total_steps,
            final_loss=s.final_loss,
        )
        for s in sessions
    ]


@router.get("/training/sessions/{session_id}/metrics", response_model=list[TrainingMetricDto])
def get_training_metrics(session_id: UUID) -> list[TrainingMetricDto]:
    """Get per-step training metrics for a session."""
    with get_session() as session:
        metrics = list(
            session.exec(
                select(TrainingMetric)
                .where(TrainingMetric.session_id == session_id)
                .order_by(TrainingMetric.step)
            ).all()
        )

    return [
        TrainingMetricDto(
            step=m.step,
            epoch=m.epoch,
            loss=m.loss,
            grad_norm=m.grad_norm,
            learning_rate=m.learning_rate,
            reward_mean=m.reward_mean,
            reward_std=m.reward_std,
            entropy=m.entropy,
            completion_mean_length=m.completion_mean_length,
            step_time_s=m.step_time_s,
        )
        for m in metrics
    ]
