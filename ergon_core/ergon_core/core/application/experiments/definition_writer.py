"""Persist a Benchmark directly into immutable definition rows.

Reads identity fields inline from the live Benchmark object graph — no
BoundExperiment intermediate, no constructor_state() serialisation.
"""

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from ergon_core.api.benchmark import Benchmark, Task, TaskSpec
from ergon_core.api.errors import SandboxKindMismatch
from ergon_core.api.rubric import Rubric
from ergon_core.core.domain.experiments import DefinitionHandle
from ergon_core.core.shared.json_types import JsonObject
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
from ergon_core.core.shared.utils import utcnow
from sqlalchemy.exc import SQLAlchemyError

if TYPE_CHECKING:
    from ergon_core.core.domain.experiments import Experiment
    from ergon_core.api.criterion import Criterion


# TODO: we need a more consistent pattern for this (there is a repository for this module but this is a grab bag of logic I think is imported from elsewhere. lets consider some archetecture (should unit tests expect that repository objects are the only methods that can be called cross module?))
# TODO: infact this module is a shining example oh how we've conflated "repository as object containing all the SQL views / reads/ rewrites with "domain logic repogisotry / constroller". this needs cleaning up.
def _task_to_definition_json(task: Task | TaskSpec) -> JsonObject:
    """Snapshot a benchmark-returned task as ``_type``-discriminated JSON.

    Two shapes are written, distinguished by the ``_type`` discriminator:

    - ``Task`` instances (PR 5+ object-bound) → full
      ``model_dump(mode="json")`` carrying ``_type``, scalar fields,
      and any inlined ``worker``/``sandbox``/``evaluators`` snapshots.
    - ``TaskSpec`` instances (PR 1 legacy) → flat fields plus a
      ``_type`` pointing at ``TaskSpec`` and a ``_legacy: True`` marker
      so ``Task.from_definition`` takes the bridge branch.

    Named ``_task_to_definition_json`` so PR 11 can grep-and-delete it
    as a single symbol once only ``Task`` remains.
    """

    if isinstance(task, Task):
        return task.model_dump(mode="json")
    return {
        "_type": "ergon_core.api.benchmark.task:TaskSpec",
        **task.model_dump(mode="json"),
        "_legacy": True,
    }


def _criterion_snapshot_name(criterion: "Criterion") -> str:
    return criterion.slug


def validate_sandbox_compatibility(benchmark: Benchmark) -> None:
    """Reject benchmarks where a task's worker requires a sandbox
    the bound ``task.sandbox`` doesn't satisfy.

    Only checks object-bound ``Task`` instances — legacy
    ``TaskSpec`` benchmarks have no inline worker/sandbox to
    validate. PR 11 makes ``Task`` the only shape and drops the
    ``isinstance(task, Task)`` branch.

    Raises ``SandboxKindMismatch`` on the first mismatch found.
    """
    for tasks in benchmark.build_instances().values():
        for task in tasks:
            if not isinstance(task, Task):
                continue
            if task.worker is None or task.sandbox is None:
                continue
            required = type(task.worker).requires_sandbox
            if not isinstance(task.sandbox, required):
                raise SandboxKindMismatch(
                    # Tasks at construction time don't have stable
                    # ids — Task.task_id raises until
                    # ``Task.from_definition`` binds it. A fresh
                    # uuid4 is enough to identify which task in
                    # the error context.
                    task_id=task._task_id if task._task_id else uuid4(),
                    component=type(task.worker).__name__,
                    required=required,
                    actual=type(task.sandbox),
                )


def persist_benchmark(benchmark: Benchmark) -> DefinitionHandle:  # noqa: C901
    """Persist a configured Benchmark as a definition row.

    Replaces ``persist_definition(experiment)`` from before PR 6.5. Identity
    fields (``name``, ``description``, ``metadata``) are read off the
    ``Benchmark`` instance directly — the ``Experiment`` wrapper that
    used to carry them is gone.

    Validates sandbox/worker compatibility before any DB write.
    """
    validate_sandbox_compatibility(benchmark)

    # ---- 1. Materialise instances / tasks ----------------------------
    instances_map = benchmark.build_instances()

    # ---- 2. Identity fields & shared bookkeeping ---------------------
    benchmark_type: str = benchmark.type_slug
    resolved_metadata: dict[str, Any] = dict(benchmark.metadata)  # slopcop: ignore[no-typing-any]
    now = utcnow()
    definition_id = uuid4()

    # -- definition row --
    definition_row = ExperimentDefinition(
        id=definition_id,
        benchmark_type=benchmark_type,
        name=benchmark.name,
        description=benchmark.description,
        created_by=benchmark.created_by,
        metadata_json=resolved_metadata,
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
                task_json=_task_to_definition_json(task),
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

    # -- evaluator rows from inline object-bound Task.evaluators --------
    # PR 10e bridge: current telemetry still requires a
    # RunTaskEvaluation.definition_evaluator_id FK, so inline public
    # evaluators are mirrored into the existing definition evaluator
    # tables until PR 11 resets the schema around task snapshots.
    evaluator_rows_by_key: dict[str, ExperimentDefinitionEvaluator] = {}
    evaluator_snapshot_by_key: dict[str, JsonObject] = {}

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

    # -- task-evaluator binding rows (from inline Task.evaluators) --
    task_evaluator_rows: list[ExperimentDefinitionTaskEvaluator] = []
    for instance_key, tasks in instances_map.items():
        for task in tasks:
            task_id = task_rows_by_key[(instance_key, task.task_slug)].id
            if task_id is None:
                raise ValueError(
                    f"Task {task.task_slug!r} has no assigned ID for evaluator binding"
                )
            inline_names_for_task: set[str] = set()
            # typing: legacy-bridge
            for index, evaluator in enumerate(
                getattr(task, "evaluators", ())  # slopcop: ignore[no-hasattr-getattr]
            ):
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

    # ---- 3. Write all rows in one transaction ------------------------
    DefinitionRow = (
        ExperimentDefinition
        | ExperimentDefinitionEvaluator
        | ExperimentDefinitionInstance
        | ExperimentDefinitionTask
        | ExperimentDefinitionTaskDependency
        | ExperimentDefinitionTaskEvaluator
    )
    all_rows: list[DefinitionRow] = [
        definition_row,
        *evaluator_rows_by_key.values(),
        *instance_rows,
        *task_rows,
        *dependency_rows,
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

    # ---- 4. Return handle --------------------------------------------
    return DefinitionHandle(
        definition_id=definition_id,
        benchmark_type=benchmark_type,
        instance_count=len(instance_rows),
        task_count=len(task_rows),
        created_at=created_at,
        metadata=resolved_metadata,
    )


class _ExperimentDefinitionWriter:
    """Writes immutable definition rows directly from a domain Experiment.

    Identity-not-serialization: rows store type slugs + model_target,
    not serialized constructor state. Runtime reconstructs fresh objects
    from registry + identity fields. snapshot_json is write-once audit
    data -- nothing reconstructs from it.

    Used by the v1 launch path (``_persist_single_sample_workflow_definition``
    in ``launch.py``) which builds domain ``Experiment`` objects with
    explicit worker/evaluator specs. PR 11 deletes this class once the
    legacy launch path is gone.
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
            name=experiment.benchmark.name,
            description=experiment.benchmark.description,
            created_by=experiment.benchmark.created_by,
            metadata_json=dict(experiment.metadata),
            created_at=now,
        )

        # -- worker rows --
        # reason: RFC 2026-04-22 §1 — ``Experiment.workers`` now holds
        # ``WorkerSpec`` descriptors. ``worker_slug`` maps 1:1 to
        # ``ExperimentDefinitionWorker.worker_type`` (registry key persisted
        # verbatim; worker_execute looks it up through the core registry).
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
                snapshot["criteria"] = [_criterion_snapshot_name(c) for c in evaluator.criteria]

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
                    task_json=_task_to_definition_json(task),
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
        return DefinitionHandle(
            definition_id=definition_id,
            benchmark_type=benchmark_type,
            worker_bindings=worker_bindings,
            evaluator_bindings=evaluator_bindings,
            instance_count=len(instance_rows),
            task_count=len(task_rows),
            created_at=created_at,
            metadata=dict(experiment.metadata),
        )
