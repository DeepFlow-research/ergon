"""Dummy sandbox manager for smoke testing - no-op implementation."""

from logging import getLogger
from pathlib import Path
from typing import TypeVar
from uuid import UUID

from e2b_code_interpreter.code_interpreter_async import AsyncSandbox
from pydantic import BaseModel

from h_arcane.core._internal.infrastructure.sandbox import (
    BaseSandboxManager,
    DownloadedFiles,
)
from h_arcane.core._internal.db.models import ResourceRecord

logger = getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class DummySandboxManager(BaseSandboxManager):
    """No-op sandbox manager for smoke testing.

    This manager implements the BaseSandboxManager interface but
    doesn't create real E2B sandboxes. All operations are no-ops
    or return mock data.

    Note: The smoke test toolkit uses stub tools that don't call
    sandbox methods, but this manager is needed for interface
    compatibility with the benchmark registry and factory patterns.
    """

    async def _install_dependencies(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        """No-op: smoke test doesn't use real sandboxes."""
        pass

    async def create(
        self,
        task_id: UUID,
        skills_dir: Path | None = None,
        timeout_minutes: int = 30,
        envs: dict[str, str] | None = None,
    ) -> str:
        """Return a dummy sandbox ID without creating a real sandbox.

        Args:
            task_id: UUID of the task
            skills_dir: Ignored for smoke test
            timeout_minutes: Ignored for smoke test
            envs: Ignored for smoke test

        Returns:
            A dummy sandbox_id string
        """
        sandbox_id = f"dummy-sandbox-{task_id}"
        logger.info(f"DummySandboxManager: created fake sandbox {sandbox_id}")
        return sandbox_id

    def get_sandbox(self, task_id: UUID) -> AsyncSandbox | None:
        """Return None - no real sandbox exists."""
        return None

    async def upload_inputs(self, task_id: UUID, resources: list[ResourceRecord]) -> None:
        """No-op: smoke test doesn't upload files to sandbox."""
        logger.debug(f"DummySandboxManager: skipping upload for {len(resources)} resources")

    async def download_all_outputs(self, task_id: UUID, output_dir: Path) -> DownloadedFiles:
        """Return empty files list - smoke test doesn't create sandbox outputs."""
        return DownloadedFiles(files=[])

    async def run_skill(
        self,
        task_id: UUID,
        skill_name: str,
        return_type: type[T],
        **kwargs,
    ) -> T:
        """Raise error - smoke test should use stub tools, not sandbox skills.

        The SmokeTestToolkit uses stub tools that return mock data directly
        without calling this method. If this is called, it indicates a
        misconfiguration.
        """
        raise NotImplementedError(
            f"DummySandboxManager.run_skill() called for skill '{skill_name}'. "
            "Smoke test uses stub tools, not sandbox skills. "
            "This indicates a misconfiguration in the smoke test toolkit."
        )

    async def terminate(self, task_id: UUID) -> None:
        """No-op: no real sandbox to terminate."""
        logger.debug(f"DummySandboxManager: terminate called for task_id={task_id} (no-op)")
