"""Object-bound dynamic task helpers for smoke fixtures."""

from ergon_core.api import Task
from ergon_core.api.worker import Worker
from ergon_core.core.application.tasks.models import SubtaskSpec
from tests.fixtures.smoke_components.sandbox import SmokePublicSandbox


def smoke_worker_for_slug(worker_slug: str, *, model: str | None) -> Worker:
    from tests.fixtures.smoke_components.benchmarks import _SMOKE_WORKERS

    worker_cls = _SMOKE_WORKERS[worker_slug]
    return worker_cls(name=worker_slug, model=model)


def smoke_task_from_spec(
    *,
    parent_task: Task,
    spec: SubtaskSpec,
    model: str | None,
) -> Task:
    worker_slug = str(spec.assigned_worker_slug)
    return Task(
        task_slug=str(spec.task_slug),
        instance_key=parent_task.instance_key,
        description=spec.description,
        parent_task_slug=parent_task.task_slug,
        dependency_task_slugs=tuple(str(dep) for dep in spec.depends_on),
        worker=smoke_worker_for_slug(worker_slug, model=model),
        sandbox=SmokePublicSandbox(),
    )
