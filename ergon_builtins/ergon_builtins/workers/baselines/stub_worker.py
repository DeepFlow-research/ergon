"""TEST FIXTURE ONLY. Do not use as a template for real workers.

Returns fixed output without calling any model. For smoke tests only.
"""

from h_arcane.api import BenchmarkTask, Worker, WorkerContext, WorkerResult


class StubWorker(Worker):
    type_slug = "stub-worker"

    def __init__(self, *, name: str = "stub", model: str | None = None) -> None:
        self.name = name
        self.model = model

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> WorkerResult:
        return WorkerResult(
            output=f"Stub output for {task.task_key}",
            success=True,
            metadata={"task_key": task.task_key, "model": self.model},
        )
