from uuid import uuid4

import pytest
from ergon_core.api.worker import SpawnedTaskHandle, WorkerOutput
from ergon_core.core.shared.context_parts import ContextPartChunk
from ergon_core.test_support.task_factory import task_with_id
from tests.fixtures.smoke_components.workers.swebench_smoke import SweBenchSadPathSmokeWorker


class _SpawnOnlyContext:
    def __init__(self) -> None:
        self.sample_id = uuid4()
        self.task_id = uuid4()
        self.execution_id = uuid4()
        self.sandbox_id = "smoke-sandbox-test"

    async def spawn_task(self, task, *, depends_on=()):
        del task, depends_on
        return SpawnedTaskHandle(task_id=uuid4())


@pytest.mark.asyncio
async def test_smoke_parent_worker_chunks_emit_observed_usage_metrics() -> None:
    worker = SweBenchSadPathSmokeWorker(name="swebench-sadpath-smoke-worker", model="openai:gpt-4o")
    task = task_with_id(
        uuid4(),
        task_slug="root",
        instance_key="astropy__astropy-12907",
        description="smoke root",
        worker=worker,
    )

    chunks: list[ContextPartChunk] = []
    async for item in worker.execute(task, context=_SpawnOnlyContext()):
        if isinstance(item, WorkerOutput):
            break
        chunks.append(item)

    assert chunks
    assert all(chunk.provider_usage is not None for chunk in chunks)
    assert all((chunk.provider_usage.total_tokens or 0) > 0 for chunk in chunks)
    assert all(chunk.provider_usage.total_cost_usd is not None for chunk in chunks)
