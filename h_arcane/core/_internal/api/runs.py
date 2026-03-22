"""FastAPI router for persisted run-detail snapshots."""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from fastapi import APIRouter, HTTPException

from h_arcane.core._internal.api.run_schemas import (
    RunActionDto,
    RunCommunicationMessageDto,
    RunCommunicationThreadDto,
    RunEvaluationCriterionDto,
    RunExecutionAttemptDto,
    RunResourceDto,
    RunSnapshotDto,
    RunTaskDto,
    RunTaskEvaluationDto,
)
from h_arcane.core._internal.db.models import Action, ResourceRecord, Run, TaskExecution, Thread
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.task.schema import TaskTreeNode
from h_arcane.core.status import TaskStatus

router = APIRouter(prefix="/runs", tags=["runs"])


def _default_task_id(task_tree: TaskTreeNode | None) -> str | None:
    if task_tree is None:
        return None
    leaves = task_tree.get_leaf_ids()
    if len(leaves) == 1:
        return str(leaves[0])
    return str(task_tree.id)


def _build_task_maps(
    task_tree: TaskTreeNode | None,
    latest_executions_by_task: dict[UUID, TaskExecution],
    current_states: dict[UUID, TaskStatus],
) -> tuple[dict[str, RunTaskDto], str, int, int, int, int, int]:
    if task_tree is None:
        return {}, "", 0, 0, 0, 0, 0

    tasks: dict[str, RunTaskDto] = {}
    completed_tasks = 0
    running_tasks = 0
    failed_tasks = 0

    for level, node in _walk_with_level(task_tree):
        latest_execution = latest_executions_by_task.get(node.id)
        status = current_states.get(node.id, TaskStatus.PENDING)
        task_id = str(node.id)
        tasks[task_id] = RunTaskDto(
            id=task_id,
            name=node.name,
            description=node.description,
            status=status,
            parent_id=str(node.parent_id) if node.parent_id else None,
            child_ids=[str(child.id) for child in node.children],
            depends_on_ids=[str(dep_id) for dep_id in node.depends_on],
            assigned_worker_id=str(node.assigned_to.id) if node.assigned_to else None,
            assigned_worker_name=node.assigned_to.name if node.assigned_to else None,
            started_at=latest_execution.started_at if latest_execution else None,
            completed_at=latest_execution.completed_at if latest_execution else None,
            is_leaf=node.is_leaf,
            level=level,
        )

        if node.is_leaf:
            if status == TaskStatus.COMPLETED:
                completed_tasks += 1
            elif status == TaskStatus.RUNNING:
                running_tasks += 1
            elif status == TaskStatus.FAILED:
                failed_tasks += 1

    return (
        tasks,
        str(task_tree.id),
        len(task_tree.walk()),
        len(task_tree.get_leaf_ids()),
        completed_tasks,
        running_tasks,
        failed_tasks,
    )


def _walk_with_level(tree: TaskTreeNode, level: int = 0) -> list[tuple[int, TaskTreeNode]]:
    nodes = [(level, tree)]
    for child in tree.children:
        nodes.extend(_walk_with_level(child, level + 1))
    return nodes


def _task_keyed_resources(resources: list[ResourceRecord]) -> dict[str, list[RunResourceDto]]:
    by_task: dict[str, list[RunResourceDto]] = defaultdict(list)
    for resource in resources:
        if resource.task_id is None:
            continue
        task_id = str(resource.task_id)
        by_task[task_id].append(
            RunResourceDto(
                id=str(resource.id),
                task_id=task_id,
                task_execution_id=str(resource.task_execution_id)
                if resource.task_execution_id
                else "",
                name=resource.name,
                mime_type=resource.mime_type,
                size_bytes=resource.size_bytes,
                file_path=resource.file_path,
                created_at=resource.created_at,
            )
        )

    return dict(by_task)


def _task_keyed_executions(
    executions: list[TaskExecution],
    agent_names: dict[str, str],
) -> dict[str, list[RunExecutionAttemptDto]]:
    by_task: dict[str, list[RunExecutionAttemptDto]] = defaultdict(list)
    for execution in sorted(executions, key=lambda item: (str(item.task_id), item.attempt_number)):
        task_id = str(execution.task_id)
        by_task[task_id].append(
            RunExecutionAttemptDto(
                id=str(execution.id),
                task_id=task_id,
                attempt_number=execution.attempt_number,
                status=execution.status,
                agent_id=str(execution.agent_id) if execution.agent_id else None,
                agent_name=agent_names.get(str(execution.agent_id)) if execution.agent_id else None,
                started_at=execution.started_at,
                completed_at=execution.completed_at,
                output_text=execution.output_text,
                output_resource_ids=list(execution.output_resource_ids or []),
                error_message=execution.error_message,
                score=execution.score,
                evaluation_details=execution.evaluation_details_for(),
            )
        )

    return dict(by_task)


def _task_keyed_actions(
    actions: list[Action],
    agent_names: dict[str, str],
    agent_to_task_ids: dict[str, list[str]],
    default_task_id: str | None,
) -> dict[str, list[RunActionDto]]:
    if default_task_id is None:
        return {}

    by_task: dict[str, list[RunActionDto]] = defaultdict(list)
    for action in actions:
        task_id = default_task_id
        if action.agent_id is not None:
            candidate_task_ids = agent_to_task_ids.get(str(action.agent_id), [])
            if len(candidate_task_ids) == 1:
                task_id = candidate_task_ids[0]

        by_task[task_id].append(
            RunActionDto(
                id=str(action.id),
                task_id=task_id,
                worker_id=str(action.agent_id) if action.agent_id else "",
                worker_name=agent_names.get(str(action.agent_id), ""),
                type=action.action_type,
                input=action.input,
                output=action.output,
                status="failed" if action.error is not None else "completed",
                started_at=action.started_at,
                completed_at=action.completed_at,
                duration_ms=action.duration_ms,
                success=action.error is None,
                error=str(action.error) if action.error is not None else None,
            )
        )

    return dict(by_task)


def _threads_snapshot(
    threads: list[Thread],
    default_task_id: str | None,
) -> list[RunCommunicationThreadDto]:
    snapshot: list[RunCommunicationThreadDto] = []
    for thread in threads:
        messages = queries.thread_messages.get_by_thread(thread.id)
        snapshot.append(
            RunCommunicationThreadDto(
                id=str(thread.id),
                run_id=str(thread.run_id),
                task_id=default_task_id,
                topic=thread.topic,
                agent_a_id=thread.agent_a_id,
                agent_b_id=thread.agent_b_id,
                created_at=thread.created_at,
                updated_at=thread.updated_at,
                messages=[
                    RunCommunicationMessageDto(
                        id=str(message.id),
                        thread_id=str(thread.id),
                        run_id=str(message.run_id),
                        task_id=default_task_id,
                        thread_topic=thread.topic,
                        from_agent_id=message.from_agent_id,
                        to_agent_id=message.to_agent_id,
                        content=message.content,
                        sequence_num=message.sequence_num,
                        created_at=message.created_at,
                    )
                    for message in messages
                ],
            )
        )
    return snapshot


def _evaluations_snapshot(run_id: UUID, default_task_id: str | None) -> dict[str, RunTaskEvaluationDto]:
    evaluation = queries.task_evaluation_results.get_by_run(run_id)
    if evaluation is None:
        return {}

    key = default_task_id or "__run__"
    criterion_results = evaluation.parsed_criterion_results()
    return {
        key: RunTaskEvaluationDto(
            id=str(evaluation.id),
            run_id=str(evaluation.run_id),
            task_id=key if default_task_id else None,
            total_score=evaluation.total_score,
            max_score=evaluation.max_score,
            normalized_score=evaluation.normalized_score,
            stages_evaluated=evaluation.stages_evaluated,
            stages_passed=evaluation.stages_passed,
            failed_gate=evaluation.failed_gate,
            created_at=evaluation.created_at,
            criterion_results=[
                RunEvaluationCriterionDto(
                    id=str(result.id),
                    stage_num=result.stage_num,
                    stage_name=result.stage_name,
                    criterion_num=result.criterion_num,
                    criterion_type=result.criterion_type,
                    criterion_description=result.criterion_description,
                    score=result.score,
                    max_score=result.max_score,
                    feedback=result.feedback,
                    evaluation_input=result.evaluation_input,
                    error=result.error,
                    evaluated_action_ids=list(result.evaluated_action_ids or []),
                    evaluated_resource_ids=list(result.evaluated_resource_ids or []),
                )
                for result in criterion_results
            ],
        )
    }


def _agent_maps(run: Run, task_tree: TaskTreeNode | None) -> tuple[dict[str, str], dict[str, list[str]]]:
    agent_names: dict[str, str] = {}
    for agent in queries.agent_configs.get_by_run(run.id):
        agent_names[str(agent.id)] = agent.name

    agent_to_task_ids: dict[str, list[str]] = defaultdict(list)
    if task_tree is None:
        return agent_names, agent_to_task_ids

    config_by_worker_id: dict[str, str] = {}
    for worker_id, config_id in (run.parsed_agent_mapping() or {}).items():
        config_by_worker_id[str(config_id)] = str(worker_id)

    worker_to_task_ids: dict[str, list[str]] = defaultdict(list)
    for task in task_tree.walk():
        worker_to_task_ids[str(task.assigned_to.id)].append(str(task.id))

    for config_id, worker_id in config_by_worker_id.items():
        agent_to_task_ids[config_id] = worker_to_task_ids.get(worker_id, [])

    return agent_names, agent_to_task_ids


def build_run_snapshot(run_id: UUID) -> RunSnapshotDto | None:
    run = queries.runs.get(run_id)
    if run is None:
        return None

    experiment = queries.experiments.get(run.experiment_id)
    if experiment is None:
        return None

    task_tree = experiment.parsed_task_tree()
    executions = queries.task_executions.get_by_run(run_id)
    latest_executions_by_task: dict[UUID, TaskExecution] = {}
    for execution in executions:
        existing = latest_executions_by_task.get(execution.task_id)
        if existing is None or execution.attempt_number >= existing.attempt_number:
            latest_executions_by_task[execution.task_id] = execution

    current_states = queries.task_state_events.get_current_states(run_id)
    (
        tasks,
        root_task_id,
        total_tasks,
        total_leaf_tasks,
        completed_tasks,
        running_tasks,
        failed_tasks,
    ) = _build_task_maps(task_tree, latest_executions_by_task, current_states)

    default_task_id = _default_task_id(task_tree)
    agent_names, agent_to_task_ids = _agent_maps(run, task_tree)

    actions = queries.actions.get_all(run_id)
    resources = queries.resources.get_by_run(run_id)
    threads = queries.threads.get_by_run(run_id)

    return RunSnapshotDto(
        id=str(run.id),
        experiment_id=str(run.experiment_id),
        name=task_tree.name if task_tree is not None else experiment.task_id,
        status=run.status,
        tasks=tasks,
        root_task_id=root_task_id,
        actions_by_task=_task_keyed_actions(actions, agent_names, agent_to_task_ids, default_task_id),
        resources_by_task=_task_keyed_resources(resources),
        executions_by_task=_task_keyed_executions(executions, agent_names),
        sandboxes_by_task={},
        threads=_threads_snapshot(threads, default_task_id),
        evaluations_by_task=_evaluations_snapshot(run_id, default_task_id),
        started_at=run.started_at or run.created_at,
        completed_at=run.completed_at,
        duration_seconds=(
            max((run.completed_at - run.started_at).total_seconds(), 0.0)
            if run.started_at and run.completed_at
            else None
        ),
        total_tasks=total_tasks,
        total_leaf_tasks=total_leaf_tasks,
        completed_tasks=completed_tasks,
        running_tasks=running_tasks,
        failed_tasks=failed_tasks,
        final_score=(
            run.normalized_score if run.normalized_score is not None else run.final_score
        ),
        error=run.error_message,
    )


@router.get("/{run_id}", response_model=RunSnapshotDto)
def get_run(run_id: UUID) -> RunSnapshotDto:
    """Get a persisted run-detail snapshot suitable for frontend hydration."""
    snapshot = build_run_snapshot(run_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return snapshot
