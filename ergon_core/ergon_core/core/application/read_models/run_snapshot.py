"""Pure read-model helpers for persisted run snapshots."""

from collections import defaultdict
from datetime import datetime
from uuid import UUID

from ergon_core.core.application.communication.models import (
    RunCommunicationMessageDto,
    RunCommunicationThreadDto,
)
from ergon_core.core.application.evaluation.dto_mapping import evaluation_row_to_dto
from ergon_core.core.application.read_models.models import (
    RunContextEventDto,
    RunExecutionAttemptDto,
    RunResourceDto,
    RunSandboxCommandDto,
    RunSandboxDto,
    RunTaskDto,
    RunTaskEvaluationDto,
)
from ergon_core.core.persistence.context.models import RunContextEvent
from ergon_core.core.persistence.definitions.models import ExperimentDefinitionWorker
from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphNode
from ergon_core.core.persistence.telemetry.models import (
    RunResource,
    RunTaskEvaluation,
    RunTaskExecution,
    Thread,
    ThreadMessage,
)


# TODO: this file / logic almost certainly duplicates the run benchmarks logic? if not it needs to be moved, renamed and laid out cleaner.
def _build_task_map(
    nodes: list[RunGraphNode],
    edges: list[RunGraphEdge],
    worker_by_binding: dict[str, ExperimentDefinitionWorker],
    task_timestamps: dict[UUID, tuple[datetime | None, datetime | None]],
) -> tuple[dict[str, RunTaskDto], str, int, int, int, int, int, int]:
    """Three clean passes using stored containment columns.

    Pass 1: node columns (parent_task_id, level) - no edge traversal.
    Pass 2: reverse lookup for child_ids and is_leaf.
    Pass 3: dependency edges -> depends_on_ids.
    """
    if not nodes:
        return {}, "", 0, 0, 0, 0, 0, 0

    task_map: dict[str, RunTaskDto] = {}

    for node in nodes:
        nid = str(node.task_id)
        worker = (
            worker_by_binding.get(node.assigned_worker_slug)
            if node.assigned_worker_slug is not None
            else None
        )
        started_at, completed_at = task_timestamps.get(node.task_id, (None, None))
        task_map[nid] = RunTaskDto(
            id=nid,
            name=node.task_slug,
            description=node.description,
            status=node.status,
            parent_id=str(node.parent_task_id) if node.parent_task_id else None,
            child_ids=[],
            depends_on_ids=[],
            is_leaf=True,
            level=node.level,
            assigned_worker_id=str(worker.id) if worker else None,
            assigned_worker_slug=node.assigned_worker_slug,
            started_at=started_at,
            completed_at=completed_at,
        )

    for nid, dto in task_map.items():
        if dto.parent_id and dto.parent_id in task_map:
            parent = task_map[dto.parent_id]
            task_map[dto.parent_id] = parent.model_copy(
                update={"child_ids": [*parent.child_ids, nid], "is_leaf": False}
            )

    for edge in edges:
        src, tgt = str(edge.source_task_id), str(edge.target_task_id)
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


def _task_keyed_executions(
    executions: list[RunTaskExecution],
    worker_map: dict[UUID, ExperimentDefinitionWorker],
) -> dict[str, list[RunExecutionAttemptDto]]:
    by_task: dict[str, list[RunExecutionAttemptDto]] = defaultdict(list)
    for ex in sorted(
        executions,
        key=lambda e: (str(e.task_id), e.attempt_number),
    ):
        tid = str(ex.task_id)
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
    for resource in resources:
        task_id_uuid = (
            execution_task_map.get(resource.task_execution_id)
            if resource.task_execution_id
            else None
        )
        if task_id_uuid is None:
            continue
        tid = str(task_id_uuid)
        by_task[tid].append(
            RunResourceDto(
                id=str(resource.id),
                task_id=tid,
                task_execution_id=(
                    str(resource.task_execution_id) if resource.task_execution_id else ""
                ),
                name=resource.name,
                mime_type=resource.mime_type,
                file_path=resource.file_path,
                size_bytes=resource.size_bytes,
                created_at=resource.created_at,
            )
        )
    return dict(by_task)


def _task_keyed_evaluations(
    evaluations: list[RunTaskEvaluation],
    run_id: str,
) -> dict[str, RunTaskEvaluationDto]:
    result: dict[str, RunTaskEvaluationDto] = {}
    for ev in evaluations:
        tid = str(ev.task_id)
        result[tid] = evaluation_row_to_dto(ev)
    return result


def _task_keyed_sandboxes(
    run_summary: dict,
) -> dict[str, RunSandboxDto]:
    """Extract sandbox info from run summary_json if available."""
    result: dict[str, RunSandboxDto] = {}
    sandboxes = run_summary.get("sandboxes", {})
    for task_id, sandbox in sandboxes.items():
        commands = [
            RunSandboxCommandDto(
                command=cmd.get("command", ""),
                stdout=cmd.get("stdout"),
                stderr=cmd.get("stderr"),
                exit_code=cmd.get("exit_code"),
                duration_ms=cmd.get("duration_ms"),
                timestamp=cmd.get("timestamp", "1970-01-01T00:00:00Z"),
            )
            for cmd in sandbox.get("commands", [])
        ]
        result[task_id] = RunSandboxDto(
            sandbox_id=sandbox.get("sandbox_id", ""),
            task_id=task_id,
            template=sandbox.get("template"),
            timeout_minutes=sandbox.get("timeout_minutes", 5),
            status=sandbox.get("status", "unknown"),
            created_at=sandbox.get("created_at", "1970-01-01T00:00:00Z"),
            closed_at=sandbox.get("closed_at"),
            close_reason=sandbox.get("close_reason"),
            commands=commands,
        )
    return result


def _build_communication_threads(
    threads: list[Thread],
    messages: list[ThreadMessage],
    execution_task_map: dict[UUID, UUID],
) -> list[RunCommunicationThreadDto]:
    msgs_by_thread: dict[UUID, list[ThreadMessage]] = defaultdict(list)
    for message in sorted(messages, key=lambda m: m.sequence_num):
        msgs_by_thread[message.thread_id].append(message)

    result: list[RunCommunicationThreadDto] = []
    for thread in threads:
        thread_messages = msgs_by_thread.get(thread.id, [])
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
                id=str(thread.id),
                run_id=str(thread.run_id),
                task_id=str(thread_task_id) if thread_task_id else None,
                topic=thread.topic,
                summary=thread.summary,
                agent_a_id=thread.agent_a_id,
                agent_b_id=thread.agent_b_id,
                created_at=thread.created_at,
                updated_at=thread.updated_at,
                messages=[
                    RunCommunicationMessageDto(
                        id=str(message.id),
                        thread_id=str(message.thread_id),
                        run_id=str(message.run_id),
                        thread_topic=thread.topic,
                        task_id=(
                            str(execution_task_map[message.task_execution_id])
                            if (
                                message.task_execution_id
                                and message.task_execution_id in execution_task_map
                            )
                            else None
                        ),
                        task_execution_id=(
                            str(message.task_execution_id) if message.task_execution_id else None
                        ),
                        from_agent_id=message.from_agent_id,
                        to_agent_id=message.to_agent_id,
                        content=message.content,
                        sequence_num=message.sequence_num,
                        created_at=message.created_at,
                    )
                    for message in thread_messages
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
    for execution in executions:
        by_task[execution.task_id].append(execution)

    for task_id, execs in by_task.items():
        started = min(
            (execution.started_at for execution in execs if execution.started_at),
            default=None,
        )
        completed = max(
            (execution.completed_at for execution in execs if execution.completed_at),
            default=None,
        )
        result[task_id] = (started, completed)
    return result


def _context_events_by_task(
    context_events_rows: list[RunContextEvent],
    execution_task_map: dict[UUID, UUID],
) -> dict[str, list[RunContextEventDto]]:
    context_events_by_task: dict[str, list[RunContextEventDto]] = defaultdict(list)
    for event in context_events_rows:
        task_id = execution_task_map.get(event.task_execution_id)
        if task_id is None:
            continue
        context_events_by_task[str(task_id)].append(
            RunContextEventDto(
                id=event.id,
                run_id=event.run_id,
                task_execution_id=event.task_execution_id,
                task_id=task_id,
                worker_binding_key=event.worker_binding_key,
                sequence=event.sequence,
                event_type=event.event_type,
                payload=event.parsed_payload(),
                created_at=event.created_at,
                started_at=event.started_at,
                completed_at=event.completed_at,
            )
        )
    return dict(context_events_by_task)
