"""TEST FIXTURE ONLY. Do not use as a template for real workers.

Returns fixed output without calling any model. For smoke tests only.
"""

from collections.abc import AsyncGenerator
from uuid import UUID

from ergon_core.api import BenchmarkTask, Worker, WorkerContext
from ergon_core.api.generation import GenerationTurn, TextPart


class StubWorker(Worker):
    type_slug = "stub-worker"

    def __init__(
        self,
        *,
        name: str,
        model: str | None,
        task_id: UUID,
        sandbox_id: str,
    ) -> None:
        super().__init__(name=name, model=model, task_id=task_id, sandbox_id=sandbox_id)

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        yield GenerationTurn(
            response_parts=[TextPart(content=f"Stub output for {task.task_slug}")],
        )
