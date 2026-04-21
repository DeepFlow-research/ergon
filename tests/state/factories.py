"""Topology builders for state tests.

Each factory creates the minimum definition rows needed to exercise
a particular graph shape, returning the UUIDs tests need for assertions.
"""

from uuid import UUID, uuid4

from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionInstance,
    ExperimentDefinitionTask,
    ExperimentDefinitionTaskDependency,
)
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import RunRecord
from sqlmodel import Session


def seed_flat_tasks(
    session: Session,
    n: int = 3,
) -> tuple[UUID, UUID, list[UUID]]:
    """n independent tasks, no dependencies."""
    def_id = uuid4()
    inst_id = uuid4()

    session.add(
        ExperimentDefinition(
            id=def_id,
            benchmark_type="test",
        )
    )
    session.add(
        ExperimentDefinitionInstance(
            id=inst_id,
            experiment_definition_id=def_id,
            instance_key="inst-0",
        )
    )

    task_ids: list[UUID] = []
    for i in range(n):
        tid = uuid4()
        task_ids.append(tid)
        session.add(
            ExperimentDefinitionTask(
                id=tid,
                experiment_definition_id=def_id,
                instance_id=inst_id,
                task_slug=f"task-{i}",
                description=f"Test task {i}",
            )
        )

    session.flush()
    return def_id, inst_id, task_ids


def seed_chain(
    session: Session,
    n: int = 3,
) -> tuple[UUID, UUID, list[UUID], list[UUID]]:
    """Linear chain: task-0 -> task-1 -> ... -> task-(n-1).

    Returns (definition_id, instance_id, task_ids, dependency_ids).
    task_ids[0] is the root (no deps), task_ids[-1] is the leaf.
    """
    def_id, inst_id, task_ids = seed_flat_tasks(session, n)

    dep_ids: list[UUID] = []
    for i in range(1, n):
        dep_id = uuid4()
        dep_ids.append(dep_id)
        session.add(
            ExperimentDefinitionTaskDependency(
                id=dep_id,
                experiment_definition_id=def_id,
                task_id=task_ids[i],
                depends_on_task_id=task_ids[i - 1],
            )
        )

    session.flush()
    return def_id, inst_id, task_ids, dep_ids


def seed_diamond(
    session: Session,
) -> tuple[UUID, UUID, list[UUID], list[UUID]]:
    """Diamond: A -> (B, C) -> D.

    Returns (definition_id, instance_id, [A, B, C, D], dependency_ids).
    """
    def_id, inst_id, task_ids = seed_flat_tasks(session, 4)
    a, b, c, d = task_ids

    dep_ids: list[UUID] = []
    for target, source in [(b, a), (c, a), (d, b), (d, c)]:
        dep_id = uuid4()
        dep_ids.append(dep_id)
        session.add(
            ExperimentDefinitionTaskDependency(
                id=dep_id,
                experiment_definition_id=def_id,
                task_id=target,
                depends_on_task_id=source,
            )
        )

    session.flush()
    return def_id, inst_id, task_ids, dep_ids


def seed_run(session: Session, definition_id: UUID) -> UUID:
    """Create a RunRecord in PENDING status."""
    run_id = uuid4()
    session.add(
        RunRecord(
            id=run_id,
            experiment_definition_id=definition_id,
            status=RunStatus.PENDING,
        )
    )
    session.flush()
    return run_id
