"""TEST FIXTURE ONLY. Do not use as a template for real workers.

Returns fixed output without calling any model. For smoke tests only.
"""

from collections.abc import AsyncGenerator

from ergon_core.api import BenchmarkTask, Worker, WorkerContext
from ergon_core.api.generation import GenerationTurn


class StubWorker(Worker):
    type_slug = "stub-worker"

    def __init__(self, *, name: str = "stub", model: str | None = None) -> None:
        super().__init__(name=name, model=model)

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        yield GenerationTurn(
            raw_response={
                "parts": [{"part_kind": "text", "content": f"Stub output for {task.task_key}"}],
            },
        )
