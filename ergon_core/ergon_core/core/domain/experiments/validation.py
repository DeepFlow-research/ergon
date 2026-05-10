"""Experiment composition validation service."""

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from ergon_core.api.benchmark import Benchmark, Task
from ergon_core.api.rubric import Evaluator

if TYPE_CHECKING:
    from ergon_core.api import Experiment


class ExperimentValidationService:
    """Validate experiment composition before persistence or launch."""

    def validate(self, experiment: "Experiment") -> None:
        experiment.benchmark.validate()
        instances = experiment.benchmark.build_instances()
        for tasks in instances.values():
            for task in tasks:
                task.worker.validate()
                for evaluator in task.evaluators:
                    evaluator.validate()

        _validate_instances(instances)


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


def _validate_instances(instances: Mapping[str, Sequence[Task]]) -> None:
    all_task_slugs_by_instance: dict[str, set[str]] = {}
    for instance_key, tasks in instances.items():
        task_slugs = _collect_task_slugs(instance_key, tasks)
        _validate_task_links(instance_key, tasks, task_slugs)
        all_task_slugs_by_instance[instance_key] = task_slugs


def _collect_task_slugs(instance_key: str, tasks: Sequence[Task]) -> set[str]:
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
    tasks: Sequence[Task],
    task_slugs: set[str],
) -> None:
    for task in tasks:
        _validate_parent_task(instance_key, task, task_slugs)
        _validate_dependency_tasks(instance_key, task, task_slugs)


def _validate_parent_task(instance_key: str, task: Task, task_slugs: set[str]) -> None:
    if task.parent_task_slug is not None and task.parent_task_slug not in task_slugs:
        raise ValueError(
            f"Unknown parent_task_slug {task.parent_task_slug!r} in instance {instance_key!r}"
        )


def _validate_dependency_tasks(instance_key: str, task: Task, task_slugs: set[str]) -> None:
    for dep_slug in task.dependency_task_slugs:
        if dep_slug not in task_slugs:
            raise ValueError(
                f"Unknown dependency_task_slug {dep_slug!r} for task "
                f"{task.task_slug!r} in instance {instance_key!r}"
            )
