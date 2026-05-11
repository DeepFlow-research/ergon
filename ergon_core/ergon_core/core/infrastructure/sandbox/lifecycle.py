"""Runtime-facing sandbox lifecycle helpers."""

import logging
from enum import StrEnum
from typing import ClassVar
from uuid import UUID

from ergon_core.api import Sandbox
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SandboxTerminationReason(StrEnum):
    TERMINATED = "terminated"
    NOT_FOUND_OR_ALREADY_CLOSED = "not_found_or_already_closed"
    MISSING_ID = "missing_id"
    ERROR = "error"


class SandboxTerminationResult(BaseModel):
    sandbox_id: str | None
    terminated: bool
    reason: SandboxTerminationReason


class SandboxLifecycleHub:
    """Process-local registry of live public Sandbox instances."""

    _shared_live: ClassVar[dict[tuple[UUID, UUID], Sandbox]] = {}
    _shared_keys_by_sandbox_id: ClassVar[dict[int, tuple[UUID, UUID]]] = {}

    def __init__(self) -> None:
        self._live = self._shared_live
        self._keys_by_sandbox_id = self._shared_keys_by_sandbox_id

    async def acquire(
        self,
        sandbox: Sandbox,
        *,
        run_id: UUID,
        task_id: UUID,
    ) -> Sandbox:
        key = (run_id, task_id)
        if key in self._live:
            return self._live[key]
        bind = getattr(sandbox, "bind_lifecycle_identity", None)
        if bind is not None:
            bind(run_id=run_id, task_id=task_id)
        await sandbox.provision()
        self._live[key] = sandbox
        self._keys_by_sandbox_id[id(sandbox)] = key
        return sandbox

    async def release(self, sandbox: Sandbox) -> None:
        key = self._keys_by_sandbox_id.pop(id(sandbox), None)
        if key is not None:
            self._live.pop(key, None)
        await sandbox.terminate()

    def discard(self, *, run_id: UUID, task_id: UUID) -> None:
        """Evict a cached sandbox after another lifecycle owner terminates it."""
        sandbox = self._live.pop((run_id, task_id), None)
        if sandbox is not None:
            self._keys_by_sandbox_id.pop(id(sandbox), None)

    async def terminate_all(self) -> None:
        for sandbox in list(self._live.values()):
            try:
                await self.release(sandbox)
            except Exception:  # slopcop: ignore[no-broad-except]
                logger.warning("Failed to release sandbox %s", sandbox, exc_info=True)


async def terminate_sandbox_by_id(sandbox_id: str | None) -> SandboxTerminationResult:
    """Terminate a sandbox behind a single runtime-facing boundary."""
    if sandbox_id is None:
        return SandboxTerminationResult(
            sandbox_id=None,
            terminated=False,
            reason=SandboxTerminationReason.MISSING_ID,
        )

    return SandboxTerminationResult(
        sandbox_id=sandbox_id,
        terminated=False,
        reason=SandboxTerminationReason.NOT_FOUND_OR_ALREADY_CLOSED,
    )
