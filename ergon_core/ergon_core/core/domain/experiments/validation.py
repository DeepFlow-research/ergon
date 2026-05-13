"""Experiment composition validation service."""

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from ergon_core.api.benchmark import Benchmark, TaskSpec
from ergon_core.api.rubric import Evaluator
from ergon_core.core.domain.experiments.worker_spec import WorkerSpec

if TYPE_CHECKING:
    from ergon_core.core.domain.experiments import Experiment


class ExperimentValidationService:
    """Validate experiment composition before persistence or launch."""

    def validate(self, experiment: "Experiment") -> None:
        experiment.benchmark.validate()
        for spec in experiment.workers.values():
            spec.validate_spec()
        for evaluator in experiment.evaluators.values():
            evaluator.validate_runtime_deps()

        _validate_required_evaluators(experiment.benchmark, experiment.evaluators)
        task_slugs_by_instance = _validate_instances(
            experiment.benchmark.build_instances(),
            set(experiment.evaluators),
        )
        _validate_assignments(experiment.assignments, experiment.workers, task_slugs_by_instance)


def _validate_required_evaluators(
    benchmark: Benchmark,
    evaluators: Mapping[str, Evaluator],
) -> None:
    if not evaluators:
        return
    required_slots = set(benchmark.evaluator_requirements())
    missing_slots = required_slots - set(evaluators)
    if missing_slots:
        missing = ", ".join(sorted(missing_slots))
        raise ValueError(f"Missing required evaluator bindings: {missing}")


def _validate_instances(
    instances: Mapping[str, Sequence[TaskSpec]],
    evaluator_keys: set[str],
) -> dict[str, set[str]]:
    all_task_slugs_by_instance: dict[str, set[str]] = {}
    for instance_key, tasks in instances.items():
        task_slugs = _collect_task_slugs(instance_key, tasks)
        _validate_task_links(instance_key, tasks, task_slugs, evaluator_keys)
        all_task_slugs_by_instance[instance_key] = task_slugs
    return all_task_slugs_by_instance


def _collect_task_slugs(instance_key: str, tasks: Sequence[TaskSpec]) -> set[str]:
    task_slugs: set[str] = set()
    for task in tasks:
        if task.instance_key != instance_key:
            raise ValueError(
                f"Task {task.task_slug!r} declares instance_key "
                f"{task.instance_key!r} but belongs to instance {instance_key!r}"
            )
        if task.task_slug in task_slugs:
            raise ValueError(f"Duplicate task_slug {task.task_slug!r} in instance {instance_key!r}")
        task_slugs.add(task.task_slug)
    return task_slugs


def _validate_task_links(
    instance_key: str,
    tasks: Sequence[TaskSpec],
    task_slugs: set[str],
    evaluator_keys: set[str],
) -> None:
    for task in tasks:
        _validate_parent_task(instance_key, task, task_slugs)
        _validate_dependency_tasks(instance_key, task, task_slugs)
        _validate_task_evaluators(task, evaluator_keys)


def _validate_parent_task(instance_key: str, task: TaskSpec, task_slugs: set[str]) -> None:
    if task.parent_task_slug is not None and task.parent_task_slug not in task_slugs:
        raise ValueError(
            f"Unknown parent_task_slug {task.parent_task_slug!r} in instance {instance_key!r}"
        )


def _validate_dependency_tasks(instance_key: str, task: TaskSpec, task_slugs: set[str]) -> None:
    for dep_slug in task.dependency_task_slugs:
        if dep_slug not in task_slugs:
            raise ValueError(
                f"Unknown dependency_task_slug {dep_slug!r} for task "
                f"{task.task_slug!r} in instance {instance_key!r}"
            )


def _validate_task_evaluators(task: TaskSpec, evaluator_keys: set[str]) -> None:
    for eval_key in task.evaluator_binding_keys:
        if eval_key not in evaluator_keys:
            raise ValueError(
                f"Task {task.task_slug!r} references undeclared evaluator binding key {eval_key!r}"
            )


def _validate_assignments(
    assignments: Mapping[str, str | Sequence[str]] | None,
    workers: Mapping[str, WorkerSpec],
    task_slugs_by_instance: Mapping[str, set[str]],
) -> None:
    if assignments is None:
        return
    all_task_slugs_flat = {ts for slugs in task_slugs_by_instance.values() for ts in slugs}
    for worker_key, task_ref in assignments.items():
        if worker_key not in workers:
            raise ValueError(f"Assignment references unknown worker key {worker_key!r}")
        task_slugs_list = [task_ref] if isinstance(task_ref, str) else task_ref
        for task_slug in task_slugs_list:
            if task_slug not in all_task_slugs_flat:
                raise ValueError(
                    f"Assignment references unknown task_slug {task_slug!r} "
                    f"for worker {worker_key!r}"
                )
