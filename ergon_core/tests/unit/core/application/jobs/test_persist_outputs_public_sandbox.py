from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ergon_core.core.jobs.resources.persist_outputs.contract import PersistOutputsRequest
from ergon_core.core.jobs.resources.persist_outputs.job import run_persist_outputs_job


class _FakeTaskExecutionService:
    def __init__(self, seen: list[str | None]) -> None:
        self._seen = seen

    async def load_task_view(self, _session, *, sample_id, task_id, sandbox_id=None):
        del sample_id, task_id
        self._seen.append(sandbox_id)
        sandbox = SimpleNamespace(
            output_path="/workspace/public-output/",
            is_live=sandbox_id == "sbx-live",
        )
        return SimpleNamespace(task=SimpleNamespace(sandbox=sandbox))


class _FakePublisher:
    publish_dirs: tuple[tuple[str, object], ...] | None = None
    sandbox: object | None = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    @classmethod
    def from_public_sandbox(cls, **kwargs):
        cls.publish_dirs = kwargs["publish_dirs"]
        cls.sandbox = kwargs["sandbox"]
        return cls(**kwargs)


class _FakePublishService:
    async def publish_sandbox_files(self, **kwargs):
        return [object(), object()]


@pytest.mark.asyncio
async def test_persist_outputs_publishes_from_public_sandbox_output_path(monkeypatch) -> None:
    from ergon_core.core.jobs.resources.persist_outputs import composition
    from ergon_core.core.jobs.resources.persist_outputs import job as module

    seen_sandbox_ids: list[str | None] = []
    monkeypatch.setattr(module, "get_session", lambda: nullcontext(object()))
    monkeypatch.setattr(
        module,
        "TaskExecutionService",
        lambda: _FakeTaskExecutionService(seen_sandbox_ids),
    )
    monkeypatch.setattr(composition, "SandboxResourcePublisher", _FakePublisher)
    monkeypatch.setattr(composition, "SampleResourcePublishService", _FakePublishService)

    result = await run_persist_outputs_job(
        PersistOutputsRequest(
            sample_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
            sandbox_id="sbx-live",
            output_dir=None,
            benchmark_type="benchmark",
        )
    )

    assert result.outputs_count == 2
    assert seen_sandbox_ids == ["sbx-live"]
    assert _FakePublisher.publish_dirs is not None
    assert _FakePublisher.publish_dirs[0][0] == "/workspace/public-output/"
