"""Persist an Experiment directly into immutable definition rows.

Reads identity fields inline from the live Experiment object graph — no
BoundExperiment intermediate, no constructor_state() serialisation.
"""

from typing import TYPE_CHECKING
from uuid import uuid4

from ergon_core.core.domain.experiments import DefinitionHandle
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionInstance,
    ExperimentDefinitionTask,
    ExperimentDefinitionTaskAssignment,
    ExperimentDefinitionTaskDependency,
    ExperimentDefinitionTaskEvaluator,
)
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.shared.utils import utcnow
from sqlalchemy.exc import SQLAlchemyError

if TYPE_CHECKING:
    from ergon_core.api import Experiment


class _ExperimentDefinitionWriter:
    """Writes immutable definition rows directly from an Experiment.

    Identity-not-serialization: rows store type slugs + model_target,
    not serialized constructor state. Runtime reconstructs fresh objects
    from registry + identity fields. snapshot_json is write-once audit
    data -- nothing reconstructs from it.
    """

    def persist_definition(  # noqa: C901
        self,
        experiment: "Experiment",
    ) -> DefinitionHandle:
        # ---- 1. Validate ------------------------------------------------
        experiment.validate()

        # ---- 2. Materialise instances / tasks ----------------------------
        instances_map = experiment.benchmark.build_instances()

        # ---- 3. Identity fields & shared bookkeeping ---------------------
        benchmark_type: str = experiment.benchmark.type_slug
        now = utcnow()
        definition_id = uuid4()

        # -- definition row --
        definition_row = ExperimentDefinition(
            id=definition_id,
            benchmark_type=benchmark_type,
            metadata_json=dict(experiment.metadata),
            created_at=now,
        )

        # -- instance + task rows (two-pass for parent resolution) --
        instance_rows: list[ExperimentDefinitionInstance] = []
        task_rows_by_key: dict[tuple[str, str], ExperimentDefinitionTask] = {}

        for instance_key, tasks in instances_map.items():
            instance_id = uuid4()
            instance_rows.append(
                ExperimentDefinitionInstance(
                    id=instance_id,
                    experiment_definition_id=definition_id,
                    instance_key=instance_key,
                    created_at=now,
                )
            )
            for task in tasks:
                task_row = ExperimentDefinitionTask(
                    id=uuid4(),
                    experiment_definition_id=definition_id,
                    instance_id=instance_id,
                    task_slug=task.task_slug,
                    description=task.description,
                    task_payload_json=task.task_payload.model_dump(mode="json"),
                    task_json=task.to_definition(),
                    created_at=now,
                )
                task_rows_by_key[(instance_key, task.task_slug)] = task_row

        # resolve parent_task_id after all IDs are assigned
        for instance_key, tasks in instances_map.items():
            for task in tasks:
                if task.parent_task_slug is not None:
                    child = task_rows_by_key[(instance_key, task.task_slug)]
                    parent = task_rows_by_key[(instance_key, task.parent_task_slug)]
                    child.parent_task_id = parent.id

        task_rows = list(task_rows_by_key.values())

        # -- dependency rows --
        dependency_rows: list[ExperimentDefinitionTaskDependency] = []
        for instance_key, tasks in instances_map.items():
            for task in tasks:
                task_id = task_rows_by_key[(instance_key, task.task_slug)].id
                if task_id is None:
                    raise ValueError(f"Task {task.task_slug!r} has no assigned ID")
                for dep_slug in task.dependency_task_slugs:
                    dep_task_id = task_rows_by_key[(instance_key, dep_slug)].id
                    if dep_task_id is None:
                        raise ValueError(f"Dependency task {dep_slug!r} has no assigned ID")
                    dependency_rows.append(
                        ExperimentDefinitionTaskDependency(
                            id=uuid4(),
                            experiment_definition_id=definition_id,
                            task_id=task_id,
                            depends_on_task_id=dep_task_id,
                            created_at=now,
                        )
                    )

        # ---- 4. Assignment rows ------------------------------------------
        assignment_rows: list[ExperimentDefinitionTaskAssignment] = []
        for instance_key, tasks in instances_map.items():
            for task in tasks:
                task_id = task_rows_by_key[(instance_key, task.task_slug)].id
                if task_id is None:
                    raise ValueError(f"Task {task.task_slug!r} has no assigned ID for assignment")
                assignment_rows.append(
                    ExperimentDefinitionTaskAssignment(
                        id=uuid4(),
                        experiment_definition_id=definition_id,
                        task_id=task_id,
                        worker_binding_key=task.worker.name,
                        created_at=now,
                    )
                )

        # -- task-evaluator binding rows --
        task_evaluator_rows: list[ExperimentDefinitionTaskEvaluator] = []
        for instance_key, tasks in instances_map.items():
            for task in tasks:
                task_id = task_rows_by_key[(instance_key, task.task_slug)].id
                if task_id is None:
                    raise ValueError(
                        f"Task {task.task_slug!r} has no assigned ID for evaluator binding"
                    )
                for evaluator in task.evaluators:
                    task_evaluator_rows.append(
                        ExperimentDefinitionTaskEvaluator(
                            id=uuid4(),
                            experiment_definition_id=definition_id,
                            task_id=task_id,
                            evaluator_binding_key=evaluator.name,
                            created_at=now,
                        )
                    )

        # ---- 5. Write all rows in one transaction ------------------------
        DefinitionRow = (
            ExperimentDefinition
            | ExperimentDefinitionInstance
            | ExperimentDefinitionTask
            | ExperimentDefinitionTaskDependency
            | ExperimentDefinitionTaskAssignment
            | ExperimentDefinitionTaskEvaluator
        )
        all_rows: list[DefinitionRow] = [
            definition_row,
            *instance_rows,
            *task_rows,
            *dependency_rows,
            *assignment_rows,
            *task_evaluator_rows,
        ]

        created_at = definition_row.created_at

        session = get_session()
        try:
            session.add_all(all_rows)
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            raise
        finally:
            session.close()

        # ---- 6. Return handle --------------------------------------------
        return DefinitionHandle(
            definition_id=definition_id,
            benchmark_type=benchmark_type,
            instance_count=len(instance_rows),
            task_count=len(task_rows),
            created_at=created_at,
            metadata=dict(experiment.metadata),
        )
