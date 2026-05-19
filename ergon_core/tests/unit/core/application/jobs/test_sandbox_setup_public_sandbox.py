from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ergon_core.core.application.jobs.models import SandboxSetupRequest
from ergon_core.core.application.jobs.sandbox_setup import run_sandbox_setup_job


class _FakeStep:
    async def run(self, _name: str, fn, *, output_type):
        del output_type
        return await fn()


class _FakeCtx:
    step = _FakeStep()


class _PublicSandbox:
    output_path = "/workspace/public-output/"

    def __init__(self) -> None:
        self.provisioned = False

    async def provision(self) -> None:
        self.provisioned = True

    @property
    def sandbox_id(self) -> str:
        if not self.provisioned:
            raise AssertionError("sandbox_id read before provision")
        return "sbx-public"


class _FakeGraphRepo:
    def __init__(self, sandbox: _PublicSandbox) -> None:
        self._sandbox = sandbox

    async def node(self, _session, *, run_id, task_id, sandbox_id=None):
        del run_id, task_id, sandbox_id
        return SimpleNamespace(task=SimpleNamespace(sandbox=self._sandbox))


@pytest.mark.asyncio
async def test_sandbox_setup_provisions_public_sandbox(monkeypatch) -> None:
    from ergon_core.core.application.jobs import sandbox_setup as module

    sandbox = _PublicSandbox()
    monkeypatch.setattr(module, "get_session", lambda: nullcontext(object()))
    monkeypatch.setattr(module, "WorkflowGraphRepository", lambda: _FakeGraphRepo(sandbox))

    result = await run_sandbox_setup_job(
        _FakeCtx(),
        SandboxSetupRequest(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=uuid4(),
            benchmark_type="benchmark",
        ),
    )

    assert result.sandbox_id == "sbx-public"
    assert result.output_dir == "/workspace/public-output/"
