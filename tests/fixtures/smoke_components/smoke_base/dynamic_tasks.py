"""Object-bound dynamic task helpers for smoke fixtures."""

from pydantic import BaseModel, Field

from ergon_core.api import Task
from ergon_core.api.worker import Worker
from ergon_core.core.persistence.shared.types import AssignedWorkerSlug, TaskSlug
from tests.fixtures.smoke_components.sandbox import SmokePublicSandbox


class SmokeChildTaskSpec(BaseModel):
    """Fixture-only shape for building object-bound smoke child tasks."""

    task_slug: TaskSlug = Field(min_length=1)
    description: str = Field(min_length=1)
    assigned_worker_slug: AssignedWorkerSlug
    depends_on: list[TaskSlug] = Field(default_factory=list)

    model_config = {"frozen": True}


def smoke_worker_for_slug(worker_slug: str, *, model: str | None) -> Worker:
    from tests.fixtures.smoke_components.benchmarks import _SMOKE_WORKERS

    worker_cls = _SMOKE_WORKERS[worker_slug]
    return worker_cls(name=worker_slug, model=model)


def smoke_task_from_spec(
    *,
    parent_task: Task,
    spec: SmokeChildTaskSpec,
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
