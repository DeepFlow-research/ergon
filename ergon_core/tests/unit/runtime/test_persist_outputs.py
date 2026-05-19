from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ergon_core.core.application.jobs.models import PersistOutputsRequest
from ergon_core.core.application.jobs.persist_outputs import run_persist_outputs_job


class _FakeGraphRepo:
    def __init__(self, seen: list[str | None]) -> None:
        self._seen = seen

    async def node(self, _session, *, run_id, task_id, sandbox_id=None):
        del run_id, task_id
        self._seen.append(sandbox_id)
        sandbox = SimpleNamespace(output_path="/workspace/public-output/")
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
    call: dict | None = None

    async def publish_sandbox_files(self, **kwargs):
        self.__class__.call = kwargs
        return [object(), object()]


@pytest.mark.asyncio
async def test_persist_outputs_publishes_public_sandbox_through_resource_service(
    monkeypatch,
) -> None:
    from ergon_core.core.application.jobs import persist_outputs as module

    seen_sandbox_ids: list[str | None] = []
    monkeypatch.setattr(module, "get_session", lambda: nullcontext(object()))
    monkeypatch.setattr(module, "WorkflowGraphRepository", lambda: _FakeGraphRepo(seen_sandbox_ids))
    monkeypatch.setattr(module, "SandboxResourcePublisher", _FakePublisher)
    monkeypatch.setattr(module, "RunResourcePublishService", _FakePublishService)

    result = await run_persist_outputs_job(
        PersistOutputsRequest(
            run_id=uuid4(),
            definition_id=uuid4(),
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
    assert _FakePublishService.call is not None
    assert _FakePublishService.call["reader"] is _FakePublishService.call["blob_store"]
