from uuid import uuid4

import pytest

from ergon_core.api import Sandbox
from ergon_core.core.infrastructure.sandbox.lifecycle import SandboxLifecycleHub


class _Sandbox(Sandbox):
    provisions: int = 0
    terminations: int = 0

    async def provision(self) -> None:
        self.provisions += 1

    async def terminate(self) -> None:
        self.terminations += 1


@pytest.mark.asyncio
async def test_lifecycle_hub_reuses_and_releases_sandbox_by_run_task_identity() -> None:
    hub = SandboxLifecycleHub()
    run_id = uuid4()
    task_id = uuid4()
    sandbox = _Sandbox()

    acquired = await hub.acquire(sandbox, run_id=run_id, task_id=task_id)
    reacquired = await hub.acquire(_Sandbox(), run_id=run_id, task_id=task_id)

    assert acquired is sandbox
    assert reacquired is sandbox
    assert sandbox.provisions == 1

    await hub.release(sandbox)

    assert sandbox.terminations == 1
    next_sandbox = _Sandbox()
    assert await hub.acquire(next_sandbox, run_id=run_id, task_id=task_id) is next_sandbox
    await hub.release(next_sandbox)


@pytest.mark.asyncio
async def test_lifecycle_hub_discards_sandbox_terminated_by_provider_cleanup() -> None:
    run_id = uuid4()
    task_id = uuid4()
    sandbox = _Sandbox()
    worker_hub = SandboxLifecycleHub()
    cleanup_hub = SandboxLifecycleHub()

    assert await worker_hub.acquire(sandbox, run_id=run_id, task_id=task_id) is sandbox

    cleanup_hub.discard(run_id=run_id, task_id=task_id)
    next_sandbox = _Sandbox()

    assert await worker_hub.acquire(next_sandbox, run_id=run_id, task_id=task_id) is next_sandbox
    assert sandbox.terminations == 0
    await worker_hub.release(next_sandbox)
