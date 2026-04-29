from collections.abc import AsyncGenerator
from uuid import uuid4

from ergon_core.api.benchmark import Task
from ergon_core.api.worker import Worker, WorkerContext, WorkerOutput
from ergon_core.api.worker.worker import WorkerStreamItem


class ContractSmokeWorker(Worker):
    type_slug = "contract-smoke-worker"

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        yield WorkerOutput(output="ok", success=True)


def test_worker_constructor_has_only_authoring_configuration() -> None:
    worker = ContractSmokeWorker(name="primary", model="stub:constant")

    assert isinstance(worker, ContractSmokeWorker)
    assert worker.name == "primary"
    assert worker.model == "stub:constant"


def test_task_carries_non_null_runtime_task_identity() -> None:
    node_id = uuid4()

    task = Task(
        task_id=node_id,
        task_slug="root",
        instance_key="default",
        description="Run root task",
    )

    assert task.task_id == node_id
