"""Sandbox manager test double."""

from __future__ import annotations

import logging
from uuid import UUID

from ergon_core.core.providers.sandbox.manager import AsyncSandbox, BaseSandboxManager
from ergon_core.test_support.sandbox.sentinel import STUB_SANDBOX_PREFIX

logger = logging.getLogger(__name__)


class _StubSandbox:
    def __init__(self, sandbox_id: str) -> None:
        self.sandbox_id = sandbox_id

    async def kill(self) -> None:
        return None


class StubSandboxManager(BaseSandboxManager):
    """No-op sandbox manager for tests."""

    async def create(
        self,
        sandbox_key: UUID,
        run_id: UUID,
        timeout_minutes: int = 30,
        envs: dict[str, str] | None = None,
        display_task_id: UUID | None = None,
    ) -> str:
        stub_id = f"{STUB_SANDBOX_PREFIX}{sandbox_key}"
        logger.info("Returning test stub sandbox id %s for task %s", stub_id, sandbox_key)
        self._ensure_registries(sandbox_key)
        self._sandboxes[sandbox_key] = _StubSandbox(stub_id)  # type: ignore[assignment]
        self._run_ids[sandbox_key] = run_id
        self._display_task_ids[sandbox_key] = display_task_id or sandbox_key
        self._sandbox_manager_classes[sandbox_key] = type(self)
        return stub_id

    async def _install_dependencies(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        return None

    async def terminate(self, task_id: UUID, reason: str = "completed") -> None:
        self._sandboxes.pop(task_id, None)
        self._file_registries.pop(task_id, None)
        self._created_files_registry.pop(task_id, None)
        self._run_ids.pop(task_id, None)
        self._display_task_ids.pop(task_id, None)
        self._sandbox_manager_classes.pop(task_id, None)

    async def reset_timeout(self, task_id: UUID, timeout_minutes: int = 30) -> bool:
        return True
