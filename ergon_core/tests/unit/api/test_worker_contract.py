from collections.abc import AsyncGenerator

from ergon_core.api.benchmark import Task
from ergon_core.api.sandbox import Sandbox
from ergon_core.api.worker import Worker, WorkerContext, WorkerOutput
from ergon_core.api.worker.worker import WorkerStreamItem


class ContractSmokeWorker(Worker):
    type_slug = "contract-smoke-worker"

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
        sandbox: Sandbox,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        yield WorkerOutput(output="ok", success=True)


def test_worker_constructor_has_only_authoring_configuration() -> None:
    worker = ContractSmokeWorker(name="primary", model="stub:constant")

    assert isinstance(worker, ContractSmokeWorker)
    assert worker.name == "primary"
    assert worker.model == "stub:constant"
