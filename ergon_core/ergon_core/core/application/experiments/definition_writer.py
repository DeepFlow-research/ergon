"""Persist a Benchmark directly into immutable definition rows.

Reads identity fields inline from the live Benchmark object graph: no
domain Experiment wrapper and no Task template bridge.
"""

from typing import Any
from uuid import uuid4

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.errors import SandboxKindMismatch
from ergon_core.core.application.experiments.handles import DefinitionHandle
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
from ergon_core.core.shared.json_types import JsonObject
from ergon_core.core.shared.utils import utcnow
from sqlalchemy.exc import SQLAlchemyError


def validate_sandbox_compatibility(benchmark: Benchmark) -> None:
    """Reject benchmarks whose worker requires a different sandbox type."""

    for tasks in benchmark.build_instances().values():
        for task in tasks:
            required = type(task.worker).requires_sandbox
            if not isinstance(task.sandbox, required):
                raise SandboxKindMismatch(
                    task_id=task._task_id if task._task_id else uuid4(),
                    component=type(task.worker).__name__,
                    required=required,
                    actual=type(task.sandbox),
                )


def persist_benchmark(benchmark: Benchmark) -> DefinitionHandle:  # noqa: C901
    """Persist a configured object-bound Benchmark as a definition row."""

    validate_sandbox_compatibility(benchmark)

    instances_map = benchmark.build_instances()
    benchmark_type: str = benchmark.type_slug
    resolved_metadata: dict[str, Any] = dict(benchmark.metadata)  # slopcop: ignore[no-typing-any]
    now = utcnow()
    definition_id = uuid4()

    definition_row = ExperimentDefinition(
        id=definition_id,
        benchmark_type=benchmark_type,
        name=benchmark.name,
        description=benchmark.description,
        created_by=benchmark.created_by,
        metadata_json=resolved_metadata,
        created_at=now,
    )

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
                task_json=task.model_dump(mode="json"),
                created_at=now,
            )
            task_rows_by_key[(instance_key, task.task_slug)] = task_row

    for instance_key, tasks in instances_map.items():
        for task in tasks:
            if task.parent_task_slug is not None:
                child = task_rows_by_key[(instance_key, task.task_slug)]
                parent = task_rows_by_key[(instance_key, task.parent_task_slug)]
                child.parent_task_id = parent.id

    task_rows = list(task_rows_by_key.values())

    worker_rows_by_key: dict[str, ExperimentDefinitionWorker] = {}
    worker_snapshot_by_key: dict[str, JsonObject] = {}
    task_assignment_rows: list[ExperimentDefinitionTaskAssignment] = []
    for instance_key, tasks in instances_map.items():
        for task in tasks:
            task_id = task_rows_by_key[(instance_key, task.task_slug)].id
            if task_id is None:
                raise ValueError(f"Task {task.task_slug!r} has no assigned ID for worker binding")
            worker = task.worker
            binding_key = worker.type_slug
            snapshot = worker.model_dump(mode="json")
            prior_snapshot = worker_snapshot_by_key.get(binding_key)
            if prior_snapshot is not None and prior_snapshot != snapshot:
                raise ValueError(
                    f"Duplicate worker binding {binding_key!r} has conflicting snapshots"
                )
            worker_snapshot_by_key[binding_key] = snapshot
            if binding_key not in worker_rows_by_key:
                if worker.model is None:
                    raise ValueError(
                        f"Worker {binding_key!r} on task {task.task_slug!r} has no model"
                    )
                worker_rows_by_key[binding_key] = ExperimentDefinitionWorker(
                    id=uuid4(),
                    experiment_definition_id=definition_id,
                    binding_key=binding_key,
                    worker_type=worker.type_slug,
                    model_target=worker.model,
                    snapshot_json=snapshot,
                    created_at=now,
                )
            task_assignment_rows.append(
                ExperimentDefinitionTaskAssignment(
                    id=uuid4(),
                    experiment_definition_id=definition_id,
                    task_id=task_id,
                    worker_binding_key=binding_key,
                    assignment_type="initial",
                    created_at=now,
                )
            )

    evaluator_rows_by_key: dict[str, ExperimentDefinitionEvaluator] = {}
    evaluator_snapshot_by_key: dict[str, JsonObject] = {}

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

    task_evaluator_rows: list[ExperimentDefinitionTaskEvaluator] = []
    for instance_key, tasks in instances_map.items():
        for task in tasks:
            task_id = task_rows_by_key[(instance_key, task.task_slug)].id
            if task_id is None:
                raise ValueError(
                    f"Task {task.task_slug!r} has no assigned ID for evaluator binding"
                )
            inline_names_for_task: set[str] = set()
            for index, evaluator in enumerate(task.evaluators):
                binding_key = evaluator.name or f"inline-{index}"
                if binding_key in inline_names_for_task:
                    raise ValueError(
                        f"Duplicate inline evaluator name {binding_key!r} "
                        f"on task {task.task_slug!r}"
                    )
                inline_names_for_task.add(binding_key)

                snapshot = evaluator.model_dump(mode="json")
                prior_snapshot = evaluator_snapshot_by_key.get(binding_key)
                if prior_snapshot is not None and prior_snapshot != snapshot:
                    raise ValueError(
                        f"Duplicate inline evaluator name {binding_key!r} "
                        "has conflicting snapshots in one definition"
                    )
                evaluator_snapshot_by_key[binding_key] = snapshot
                if binding_key not in evaluator_rows_by_key:
                    evaluator_rows_by_key[binding_key] = ExperimentDefinitionEvaluator(
                        id=uuid4(),
                        experiment_definition_id=definition_id,
                        binding_key=binding_key,
                        evaluator_type=evaluator.type_slug,
                        snapshot_json=snapshot,
                        created_at=now,
                    )
                task_evaluator_rows.append(
                    ExperimentDefinitionTaskEvaluator(
                        id=uuid4(),
                        experiment_definition_id=definition_id,
                        task_id=task_id,
                        evaluator_binding_key=binding_key,
                        created_at=now,
                    )
                )
    DefinitionRow = (
        ExperimentDefinition
        | ExperimentDefinitionEvaluator
        | ExperimentDefinitionInstance
        | ExperimentDefinitionTask
        | ExperimentDefinitionTaskAssignment
        | ExperimentDefinitionTaskDependency
        | ExperimentDefinitionTaskEvaluator
        | ExperimentDefinitionWorker
    )
    all_rows: list[DefinitionRow] = [
        definition_row,
        *worker_rows_by_key.values(),
        *evaluator_rows_by_key.values(),
        *instance_rows,
        *task_rows,
        *task_assignment_rows,
        *dependency_rows,
        *task_evaluator_rows,
    ]

    session = get_session()
    try:
        session.add_all(all_rows)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise
    finally:
        session.close()

    return DefinitionHandle(
        definition_id=definition_id,
        benchmark_type=benchmark_type,
        instance_count=len(instance_rows),
        task_count=len(task_rows),
        created_at=now,
        metadata=resolved_metadata,
    )
