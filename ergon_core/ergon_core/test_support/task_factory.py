"""Construct a Task with `_task_id` bound, for use in unit tests.

``task_id`` is a ``PrivateAttr`` on ``Task`` so it does not round-trip
through the public Pydantic constructor. Runtime code binds it via
``Task.from_definition``; tests use this helper to keep the binding
explicit at one site.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from ergon_core.api.sandbox.sandbox import Sandbox
from ergon_core.api.benchmark.task import Task
from ergon_core.api.worker.worker import Worker
from ergon_core.api.worker.results import WorkerOutput


class TestSandbox(Sandbox):
    async def provision(self) -> None:
        return None

    async def _bind_runtime(self, sandbox_id: str) -> None:
        return None


class TestWorker(Worker):
    type_slug = "test-worker"

    async def execute(self, task: Task, *, context: object):
        yield WorkerOutput(output="ok")


def task_with_id(
    task_id: UUID,
    /,
    *,
    cls: type[Task] = Task,
    **kwargs: Any,
) -> Task:
    """Construct a `cls(**kwargs)` and bind `_task_id` to `task_id`.

    ``cls`` defaults to the base `Task`. Pass a parametrized form like
    ``Task[MyPayload]`` to constrain ``task_payload`` validation in
    the same shape as production materialization.
    """

    kwargs.setdefault("worker", TestWorker(name="worker", model="test:none"))
    kwargs.setdefault("sandbox", TestSandbox())
    task = cls(**kwargs)
    task._task_id = task_id
    return task
