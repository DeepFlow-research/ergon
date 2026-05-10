from uuid import uuid4

import pytest

from ergon_core.api import Sandbox, TaskNotMaterializedError, Worker
from ergon_core.api.benchmark import EmptyTaskPayload, Task
from ergon_core.api.worker import WorkerContext, WorkerOutput, WorkerStreamItem
from collections.abc import AsyncGenerator


class _Sandbox(Sandbox):
    async def provision(self) -> None:
        pass


class _Worker(Worker):
    type_slug = "task-test-worker"

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
        sandbox: Sandbox,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        yield WorkerOutput(output=task.task_slug, success=True)


def test_task_is_definition_time_until_materialized() -> None:
    task = Task(
        task_slug="root",
        instance_key="default",
        description="Definition-time task",
        worker=_Worker(name="worker", model="stub:model"),
        sandbox=_Sandbox(),
        task_payload=EmptyTaskPayload(),
    )

    assert task.task_slug == "root"
    with pytest.raises(TaskNotMaterializedError):
        task.task_id


def test_worker_task_requires_runtime_graph_node_identity() -> None:
    node_id = uuid4()

    definition = Task(
        task_slug="root",
        instance_key="default",
        description="Runtime task",
        worker=_Worker(name="worker", model="stub:model"),
        sandbox=_Sandbox(),
    )
    task = Task.from_definition(definition.model_dump(), task_id=node_id)

    assert task.task_id == node_id


def test_worker_task_rejects_missing_runtime_identity() -> None:
    task = Task(
        task_slug="root",
        instance_key="default",
        description="Runtime task",
        worker=_Worker(name="worker", model="stub:model"),
        sandbox=_Sandbox(),
    )

    with pytest.raises(TaskNotMaterializedError, match="has no task_id"):
        task.task_id
