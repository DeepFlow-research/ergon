"""Generic benchmark loading utilities."""

import sys
from typing import TYPE_CHECKING, Callable, Iterator, TypeVar

from h_arcane.core._internal.task.persistence import persist_workflow
from h_arcane.core._internal.task.validation import validate_task_dag
from h_arcane.core.task import Task

if TYPE_CHECKING:
    from uuid import UUID

    from h_arcane.core.worker import BaseWorker

T = TypeVar("T")


def load_benchmark_to_database(
    items: Iterator[T],
    item_to_task: Callable[[T, "BaseWorker"], Task],
    benchmark_name: str,
    worker: "BaseWorker",
    total: int | None = None,
) -> list["UUID"]:
    """Generic loader for any benchmark.

    This function provides a standard pattern for loading benchmark items
    into the database using the Task persistence layer.

    Args:
        items: Iterator of benchmark-specific items (tasks, problems, samples, etc.)
        item_to_task: Function that converts an item to a Task object
        benchmark_name: The benchmark name string (e.g., "gdpeval", "minif2f")
        worker: The worker to assign to tasks
        total: Optional total count for progress display

    Returns:
        List of created experiment UUIDs

    Example:
        >>> def item_to_task(item: GDPEvalTask, worker: BaseWorker) -> Task:
        ...     return Task(name=item.task_id, description=item.description, ...)
        >>> experiment_ids = load_benchmark_to_database(
        ...     items=iter(tasks),
        ...     item_to_task=item_to_task,
        ...     benchmark_name="gdpeval",
        ...     worker=worker,
        ...     total=len(tasks),
        ... )
    """
    from uuid import UUID

    experiment_ids: list[UUID] = []

    for idx, item in enumerate(items, 1):
        if total:
            print(f"   Processing {idx}/{total}...", file=sys.stderr, flush=True)

        task = item_to_task(item, worker)
        validate_task_dag(task)
        experiment, _, _ = persist_workflow(task, benchmark_name=benchmark_name)
        experiment_ids.append(experiment.id)

    return experiment_ids
