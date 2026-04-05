"""Pure DAG state functions for task propagation.

Reads ExperimentDefinitionTaskDependency to determine which tasks are ready
and writes RunTaskStateEvent to track state transitions. No process-local
state — everything goes through the database.
"""

from typing import Any
from uuid import UUID

from h_arcane.core.persistence.definitions.models import (
    ExperimentDefinitionTask,
    ExperimentDefinitionTaskDependency,
)
from h_arcane.core.persistence.shared.enums import TaskExecutionStatus
from h_arcane.core.persistence.telemetry.models import RunTaskStateEvent
from h_arcane.core.utils import utcnow
from sqlmodel import Session, select

# ---------------------------------------------------------------------------
# State-event helpers
# ---------------------------------------------------------------------------

def _record_state_event(
    session: Session,
    run_id: UUID,
    task_id: UUID,
    new_status: str,
    *,
    old_status: str | None = None,
    execution_id: UUID | None = None,
    event_metadata: dict[str, Any] | None = None,
) -> RunTaskStateEvent:
    evt = RunTaskStateEvent(
        run_id=run_id,
        definition_task_id=task_id,
        task_execution_id=execution_id,
        event_type="state_change",
        old_status=old_status,
        new_status=new_status,
        event_metadata=event_metadata or {},
        created_at=utcnow(),
    )
    session.add(evt)
    session.flush()
    return evt


# ---------------------------------------------------------------------------
# Mark helpers
# ---------------------------------------------------------------------------

def mark_task_ready(session: Session, run_id: UUID, task_id: UUID) -> None:
    old = get_current_task_status(session, run_id, task_id)
    _record_state_event(session, run_id, task_id, TaskExecutionStatus.PENDING, old_status=old)


def mark_task_running(
    session: Session, run_id: UUID, task_id: UUID, execution_id: UUID
) -> None:
    old = get_current_task_status(session, run_id, task_id)
    _record_state_event(
        session, run_id, task_id, TaskExecutionStatus.RUNNING,
        old_status=old, execution_id=execution_id,
    )


def mark_task_completed(
    session: Session, run_id: UUID, task_id: UUID, execution_id: UUID
) -> None:
    old = get_current_task_status(session, run_id, task_id)
    _record_state_event(
        session, run_id, task_id, TaskExecutionStatus.COMPLETED,
        old_status=old, execution_id=execution_id,
    )


def mark_task_failed(
    session: Session,
    run_id: UUID,
    task_id: UUID,
    error: str,
    execution_id: UUID | None = None,
) -> None:
    old = get_current_task_status(session, run_id, task_id)
    _record_state_event(
        session, run_id, task_id, TaskExecutionStatus.FAILED,
        old_status=old, execution_id=execution_id,
        event_metadata={"error": error},
    )


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_current_task_status(session: Session, run_id: UUID, task_id: UUID) -> str | None:
    """Return the most recent status for *task_id* in this run, or None."""
    stmt = (
        select(RunTaskStateEvent.new_status)
        .where(
            RunTaskStateEvent.run_id == run_id,
            RunTaskStateEvent.definition_task_id == task_id,
        )
        .order_by(RunTaskStateEvent.created_at.desc())
        .limit(1)
    )
    return session.exec(stmt).first()


def get_initial_ready_tasks(
    session: Session, run_id: UUID, definition_id: UUID
) -> list[UUID]:
    """Return task IDs that have zero dependencies (leaf/root tasks)."""
    all_tasks_stmt = select(ExperimentDefinitionTask.id).where(
        ExperimentDefinitionTask.experiment_definition_id == definition_id,
    )
    all_task_ids = set(session.exec(all_tasks_stmt).all())

    tasks_with_deps_stmt = select(ExperimentDefinitionTaskDependency.task_id).where(
        ExperimentDefinitionTaskDependency.experiment_definition_id == definition_id,
    )
    tasks_with_deps = set(session.exec(tasks_with_deps_stmt).all())

    ready_ids = list(all_task_ids - tasks_with_deps)

    for tid in ready_ids:
        mark_task_ready(session, run_id, tid)

    session.commit()
    return ready_ids


# ---------------------------------------------------------------------------
# Propagation
# ---------------------------------------------------------------------------

def on_task_completed(
    session: Session,
    run_id: UUID,
    definition_id: UUID,
    task_id: UUID,
    execution_id: UUID,
) -> list[UUID]:
    """Mark *task_id* completed, then find and mark newly-ready dependents.

    For each task that lists *task_id* as a dependency
    (ExperimentDefinitionTaskDependency.depends_on_task_id == task_id),
    check whether ALL of its dependencies are now COMPLETED.
    If yes, mark it PENDING (ready) and include it in the return list.
    """
    mark_task_completed(session, run_id, task_id, execution_id)

    dependent_edges_stmt = select(ExperimentDefinitionTaskDependency).where(
        ExperimentDefinitionTaskDependency.experiment_definition_id == definition_id,
        ExperimentDefinitionTaskDependency.depends_on_task_id == task_id,
    )
    dependent_edges = list(session.exec(dependent_edges_stmt).all())

    candidate_task_ids = {e.task_id for e in dependent_edges}

    newly_ready: list[UUID] = []
    for candidate_id in candidate_task_ids:
        all_deps_stmt = select(ExperimentDefinitionTaskDependency.depends_on_task_id).where(
            ExperimentDefinitionTaskDependency.experiment_definition_id == definition_id,
            ExperimentDefinitionTaskDependency.task_id == candidate_id,
        )
        dep_task_ids = list(session.exec(all_deps_stmt).all())

        if all(
            get_current_task_status(session, run_id, dep_id) == TaskExecutionStatus.COMPLETED
            for dep_id in dep_task_ids
        ):
            mark_task_ready(session, run_id, candidate_id)
            newly_ready.append(candidate_id)

    session.commit()
    return newly_ready


# ---------------------------------------------------------------------------
# Terminal-state checks
# ---------------------------------------------------------------------------

def _get_all_leaf_task_ids(session: Session, definition_id: UUID) -> list[UUID]:
    """Leaf tasks = tasks that have no dependencies pointing to them as depends_on.
    Actually, we want tasks with no *dependents* — i.e. nothing depends on them.
    These are the terminal/sink tasks in the DAG."""
    all_tasks_stmt = select(ExperimentDefinitionTask.id).where(
        ExperimentDefinitionTask.experiment_definition_id == definition_id,
    )
    all_task_ids = set(session.exec(all_tasks_stmt).all())

    depended_on_stmt = select(ExperimentDefinitionTaskDependency.depends_on_task_id).where(
        ExperimentDefinitionTaskDependency.experiment_definition_id == definition_id,
    )
    depended_on_ids = set(session.exec(depended_on_stmt).all())

    return list(all_task_ids - depended_on_ids)


def is_workflow_complete(session: Session, run_id: UUID, definition_id: UUID) -> bool:
    """True when every task in the definition has reached COMPLETED."""
    all_tasks_stmt = select(ExperimentDefinitionTask.id).where(
        ExperimentDefinitionTask.experiment_definition_id == definition_id,
    )
    all_task_ids = list(session.exec(all_tasks_stmt).all())
    if not all_task_ids:
        return True

    return all(
        get_current_task_status(session, run_id, tid) == TaskExecutionStatus.COMPLETED
        for tid in all_task_ids
    )


def is_workflow_failed(session: Session, run_id: UUID, definition_id: UUID) -> bool:
    """True when any task in the definition has reached FAILED."""
    all_tasks_stmt = select(ExperimentDefinitionTask.id).where(
        ExperimentDefinitionTask.experiment_definition_id == definition_id,
    )
    all_task_ids = list(session.exec(all_tasks_stmt).all())

    return any(
        get_current_task_status(session, run_id, tid) == TaskExecutionStatus.FAILED
        for tid in all_task_ids
    )
