"""Persist an Experiment directly into immutable definition rows.

Reads identity fields inline from the live Experiment object graph — no
BoundExperiment intermediate, no constructor_state() serialisation.
"""

from typing import TYPE_CHECKING
from uuid import uuid4

from ergon_core.api.evaluator import Rubric
from ergon_core.api.handles import PersistedExperimentDefinition
from ergon_core.api.json_types import JsonObject
from sqlalchemy.exc import SQLAlchemyError
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionEvaluator,
    ExperimentDefinitionInstance,
    ExperimentDefinitionTask,
    ExperimentDefinitionTaskAssignment,
    ExperimentDefinitionTaskDependency,
    ExperimentDefinitionTaskEvaluator,
    ExperimentDefinitionWorker,
)
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.utils import utcnow

if TYPE_CHECKING:
    from ergon_core.api.experiment import Experiment


class ExperimentPersistenceService:
    """Writes immutable definition rows directly from an Experiment.

    Identity-not-serialization: rows store type slugs + model_target,
    not serialized constructor state. Runtime reconstructs fresh objects
    from registry + identity fields. snapshot_json is write-once audit
    data -- nothing reconstructs from it.
    """

    def persist_definition(
        self,
        experiment: "Experiment",
    ) -> PersistedExperimentDefinition:
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

        # -- worker rows --
        # reason: RFC 2026-04-22 §1 — ``Experiment.workers`` now holds
        # ``WorkerSpec`` descriptors. ``worker_slug`` maps 1:1 to
        # ``ExperimentDefinitionWorker.worker_type`` (registry key persisted
        # verbatim; worker_execute looks it up back through ``WORKERS``).
        worker_rows: list[ExperimentDefinitionWorker] = []
        worker_bindings: dict[str, str] = {}

        for binding_key, spec in experiment.workers.items():
            worker_rows.append(
                ExperimentDefinitionWorker(
                    id=uuid4(),
                    experiment_definition_id=definition_id,
                    binding_key=binding_key,
                    worker_type=spec.worker_slug,
                    model_target=spec.model,
                    snapshot_json={"name": spec.name, "model": spec.model},
                    created_at=now,
                )
            )
            worker_bindings[binding_key] = spec.worker_slug

        # -- evaluator rows --
        evaluator_rows: list[ExperimentDefinitionEvaluator] = []
        evaluator_bindings: dict[str, str] = {}

        for binding_key, evaluator in experiment.evaluators.items():
            snapshot: JsonObject = {"name": evaluator.name}
            if isinstance(evaluator, Rubric):
                snapshot["criteria"] = [c.name for c in evaluator.criteria]

            evaluator_rows.append(
                ExperimentDefinitionEvaluator(
                    id=uuid4(),
                    experiment_definition_id=definition_id,
                    binding_key=binding_key,
                    evaluator_type=evaluator.type_slug,
                    snapshot_json=snapshot,
                    created_at=now,
                )
            )
            evaluator_bindings[binding_key] = evaluator.type_slug

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

        if experiment.assignments is None and len(experiment.workers) == 1:
            sole_key = next(iter(experiment.workers))
            for task_row in task_rows:
                if task_row.id is None:
                    raise ValueError("Task row has no assigned ID for assignment")
                assignment_rows.append(
                    ExperimentDefinitionTaskAssignment(
                        id=uuid4(),
                        experiment_definition_id=definition_id,
                        task_id=task_row.id,
                        worker_binding_key=sole_key,
                        created_at=now,
                    )
                )
        elif experiment.assignments is not None:
            for worker_key, task_ref in experiment.assignments.items():
                task_slugs = [task_ref] if isinstance(task_ref, str) else list(task_ref)
                for tk in task_slugs:
                    for (inst_key, t_key), task_row in task_rows_by_key.items():
                        if t_key == tk:
                            if task_row.id is None:
                                raise ValueError(
                                    f"Task {t_key!r} has no assigned ID for assignment"
                                )
                            assignment_rows.append(
                                ExperimentDefinitionTaskAssignment(
                                    id=uuid4(),
                                    experiment_definition_id=definition_id,
                                    task_id=task_row.id,
                                    worker_binding_key=worker_key,
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
                for eval_key in task.evaluator_binding_keys:
                    task_evaluator_rows.append(
                        ExperimentDefinitionTaskEvaluator(
                            id=uuid4(),
                            experiment_definition_id=definition_id,
                            task_id=task_id,
                            evaluator_binding_key=eval_key,
                            created_at=now,
                        )
                    )

        # ---- 5. Write all rows in one transaction ------------------------
        DefinitionRow = (
            ExperimentDefinition
            | ExperimentDefinitionWorker
            | ExperimentDefinitionEvaluator
            | ExperimentDefinitionInstance
            | ExperimentDefinitionTask
            | ExperimentDefinitionTaskDependency
            | ExperimentDefinitionTaskAssignment
            | ExperimentDefinitionTaskEvaluator
        )
        all_rows: list[DefinitionRow] = [
            definition_row,
            *worker_rows,
            *evaluator_rows,
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
        return PersistedExperimentDefinition(
            definition_id=definition_id,
            benchmark_type=benchmark_type,
            worker_bindings=worker_bindings,
            evaluator_bindings=evaluator_bindings,
            instance_count=len(instance_rows),
            task_count=len(task_rows),
            created_at=created_at,
            metadata=dict(experiment.metadata),
        )
