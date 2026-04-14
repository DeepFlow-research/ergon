"""FastAPI router for persisted run-detail snapshots."""

from collections import defaultdict
from datetime import datetime
from statistics import mean
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from ergon_core.core.api.schemas import (
    RunCommunicationMessageDto,
    RunCommunicationThreadDto,
    RunEvaluationCriterionDto,
    RunExecutionAttemptDto,
    RunResourceDto,
    RunSandboxCommandDto,
    RunSandboxDto,
    RunSnapshotDto,
    RunTaskDto,
    RunGenerationTurnDto,
    RunTaskEvaluationDto,
    TrainingCurvePointDto,
    TrainingMetricDto,
    TrainingSessionDto,
)
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionTask,
    ExperimentDefinitionTaskAssignment,
    ExperimentDefinitionTaskDependency,
    ExperimentDefinitionWorker,
)
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.persistence.graph.models import RunGraphNode
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
from sqlmodel import Session, select

router = APIRouter(prefix="/runs", tags=["runs"])


# ---------------------------------------------------------------------------
# Task tree helpers
# ---------------------------------------------------------------------------


def _build_task_tree(
    tasks: list[ExperimentDefinitionTask],
    dependencies: list[ExperimentDefinitionTaskDependency],
    current_statuses: dict[UUID, str],
    worker_assignments: dict[UUID, tuple[str | None, str | None]],
    task_timestamps: dict[UUID, tuple[datetime | None, datetime | None]],
) -> tuple[dict[str, RunTaskDto], str, int, int, int, int, int]:
    """Build the flat task map and counts.

    Returns (task_map, root_task_id, total, total_leaf, completed, failed, running).
    """
    if not tasks:
        return {}, "", 0, 0, 0, 0, 0

    children_map: dict[UUID, list[UUID]] = defaultdict(list)
    for t in tasks:
        if t.parent_task_id is not None:
            children_map[t.parent_task_id].append(t.id)

    deps_map: dict[UUID, list[UUID]] = defaultdict(list)
    for d in dependencies:
        deps_map[d.task_id].append(d.depends_on_task_id)

    task_by_id = {t.id: t for t in tasks}

    def _level(t: ExperimentDefinitionTask) -> int:
        depth = 0
        current = t
        while current.parent_task_id is not None:
            depth += 1
            parent = task_by_id.get(current.parent_task_id)
            if parent is None:
                break
            current = parent
        return depth

    root_id: str = ""
    result: dict[str, RunTaskDto] = {}
    completed = 0
    failed = 0
    running = 0
    leaf_count = 0

    for t in tasks:
        tid = str(t.id)
        child_ids = children_map.get(t.id, [])
        is_leaf = len(child_ids) == 0
        status = current_statuses.get(t.id, "pending")

        if t.parent_task_id is None:
            root_id = tid

        if is_leaf:
            leaf_count += 1
            if status in (TaskExecutionStatus.COMPLETED, "completed"):
                completed += 1
            elif status in (TaskExecutionStatus.FAILED, "failed"):
                failed += 1
            elif status in (TaskExecutionStatus.RUNNING, "running"):
                running += 1

        worker_id, worker_name = worker_assignments.get(t.id, (None, None))
        started_at_str, completed_at_str = task_timestamps.get(t.id, (None, None))

        result[tid] = RunTaskDto(
            id=tid,
            name=t.task_key,
            description=t.description,
            status=status,
            parent_id=str(t.parent_task_id) if t.parent_task_id else None,
            child_ids=[str(c) for c in child_ids],
            depends_on_ids=[str(d) for d in deps_map.get(t.id, [])],
            is_leaf=is_leaf,
            level=_level(t),
            assigned_worker_id=worker_id,
            assigned_worker_name=worker_name,
            started_at=started_at_str,
            completed_at=completed_at_str,
        )

    return result, root_id, len(tasks), leaf_count, completed, failed, running


# ---------------------------------------------------------------------------
# Per-task keyed helpers
# ---------------------------------------------------------------------------


def _task_keyed_executions(
    executions: list[RunTaskExecution],
    worker_map: dict[UUID, ExperimentDefinitionWorker],
) -> dict[str, list[RunExecutionAttemptDto]]:
    by_task: dict[str, list[RunExecutionAttemptDto]] = defaultdict(list)
    for ex in sorted(executions, key=lambda e: (str(e.definition_task_id), e.attempt_number)):
        tid = str(ex.definition_task_id)
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
                output_text=ex.output_text,
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
) -> dict[str, RunTaskEvaluationDto]:
    result: dict[str, RunTaskEvaluationDto] = {}
    for ev in evaluations:
        tid = str(ev.definition_task_id)
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


def _current_task_statuses(session: Session, run_id: UUID) -> dict[UUID, str]:
    """Read current task statuses from RunGraphNode (single source of truth)."""
    nodes = session.exec(
        select(RunGraphNode.definition_task_id, RunGraphNode.status).where(
            RunGraphNode.run_id == run_id
        )
    ).all()
    return {defn_id: status for defn_id, status in nodes if defn_id is not None}


def _task_timestamps(
    executions: list[RunTaskExecution],
) -> dict[UUID, tuple[datetime | None, datetime | None]]:
    """Derive per-task started_at/completed_at from execution records."""
    result: dict[UUID, tuple[datetime | None, datetime | None]] = {}
    by_task: dict[UUID, list[RunTaskExecution]] = defaultdict(list)
    for ex in executions:
        by_task[ex.definition_task_id].append(ex)

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

    # Task tree from definition tables
    tasks_stmt = select(ExperimentDefinitionTask).where(
        ExperimentDefinitionTask.experiment_definition_id == def_id
    )
    def_tasks = list(session.exec(tasks_stmt).all())

    deps_stmt = select(ExperimentDefinitionTaskDependency).where(
        ExperimentDefinitionTaskDependency.experiment_definition_id == def_id
    )
    def_deps = list(session.exec(deps_stmt).all())

    # Worker definitions for this experiment
    workers_stmt = select(ExperimentDefinitionWorker).where(
        ExperimentDefinitionWorker.experiment_definition_id == def_id
    )
    def_workers = list(session.exec(workers_stmt).all())
    worker_by_id: dict[UUID, ExperimentDefinitionWorker] = {w.id: w for w in def_workers}
    worker_by_binding: dict[str, ExperimentDefinitionWorker] = {
        w.binding_key: w for w in def_workers
    }

    # Task-to-worker assignments
    assignments_stmt = select(ExperimentDefinitionTaskAssignment).where(
        ExperimentDefinitionTaskAssignment.experiment_definition_id == def_id
    )
    assignments = list(session.exec(assignments_stmt).all())
    worker_assignments: dict[UUID, tuple[str | None, str | None]] = {}
    for a in assignments:
        w = worker_by_binding.get(a.worker_binding_key)
        if w:
            worker_assignments[a.task_id] = (str(w.id), w.binding_key)

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
    current_statuses = _current_task_statuses(session, run_id)
    timestamps = _task_timestamps(executions)
    (
        task_map,
        root_task_id,
        total_tasks,
        total_leaf,
        completed_tasks,
        failed_tasks,
        running_tasks,
    ) = _build_task_tree(def_tasks, def_deps, current_statuses, worker_assignments, timestamps)

    execution_task_map: dict[UUID, UUID] = {ex.id: ex.definition_task_id for ex in executions}

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
        evaluations_by_task=_task_keyed_evaluations(evaluations, run_id_str),
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
