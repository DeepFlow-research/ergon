"""ResearchRubrics sandbox manager.

Subclasses ``BaseSandboxManager`` to pre-install research tooling (``exa-py``)
and scaffold the workspace directory layout used by the research toolkit's
skill handlers.  Provides a ``publisher_for`` factory so toolkit methods can
trigger ``SandboxResourcePublisher.sync()`` after write operations.
"""

import logging
from typing import ClassVar
from uuid import UUID

from ergon_core.core.providers.sandbox.manager import BaseSandboxManager
from ergon_core.core.providers.sandbox.resource_publisher import (
    SandboxResourcePublisher,
)

try:
    from e2b_code_interpreter import AsyncSandbox  # type: ignore[import-untyped]
except ImportError:
    AsyncSandbox = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

# Workspace directories created inside the sandbox at provision time.
_WORKSPACE_DIRS: tuple[str, ...] = (
    "/workspace/scratchpad",
    "/workspace/final_output",
    "/workspace/researchers",
)

# Python packages installed in the sandbox at provision time.
_INSTALL_PACKAGES: tuple[str, ...] = ("exa-py>=1.0.0",)


class ResearchRubricsSandboxManager(BaseSandboxManager):
    """Singleton sandbox manager for researchrubrics benchmarks.

    One ``AsyncSandbox`` per root task.  ``exa-py`` is installed and the
    workspace directory tree is scaffolded at ``create`` time via the
    ``_install_dependencies`` override.  ``EXA_API_KEY`` from ``settings``
    is injected into the sandbox process env so the in-sandbox Exa
    skill calls (``exa_search``, ``exa_qa``, ``exa_get_content``) can
    authenticate.

    Inherits singleton ``__new__`` from ``BaseSandboxManager`` -- do NOT
    re-declare it here.
    """

    type_slug: ClassVar[str] = "researchrubrics"

    # In-sandbox tool keys sourced from ``settings``.  The base class's
    # ``_compose_envs`` helper reads ``settings.exa_api_key`` and merges
    # it into the ``envs`` dict threaded to ``AsyncSandbox.create``.
    required_env_keys: ClassVar[tuple[str, ...]] = ("EXA_API_KEY",)

    # ------------------------------------------------------------------
    # Abstract method implementation
    # ------------------------------------------------------------------

    async def _install_dependencies(
        self,
        sandbox: "AsyncSandbox",  # type: ignore[name-defined]
        task_id: UUID,
    ) -> None:
        """Install research packages and create the workspace layout."""
        if AsyncSandbox is None:
            # The class-level ``try: from e2b_code_interpreter ...`` lets us
            # import this module when e2b isn't installed (documentation builds,
            # type-only contexts).  Reaching this method with no e2b means
            # somebody constructed the manager without the optional dep --
            # fail fast with a clear message instead of a confusing
            # ``NoneType is not callable`` deeper down.
            raise RuntimeError(
                "e2b_code_interpreter is not installed; install the 'sandbox' "
                "extra (``pip install ergon[sandbox]``) or ``uv sync`` with the "
                "default groups to use ResearchRubricsSandboxManager."
            )

        for pkg in _INSTALL_PACKAGES:
            result = await sandbox.commands.run(
                f"pip install '{pkg}'",
                timeout=120,
            )
            if result.exit_code != 0:
                logger.warning(
                    "pip install %s exited %d for task %s: %s",
                    pkg,
                    result.exit_code,
                    task_id,
                    result.stderr,
                )

        for directory in _WORKSPACE_DIRS:
            await sandbox.commands.run(f"mkdir -p {directory}")

    # ------------------------------------------------------------------
    # Publisher factory
    # ------------------------------------------------------------------

    def publisher_for(
        self,
        *,
        task_id: UUID,
        run_id: UUID,
        task_execution_id: UUID,
    ) -> SandboxResourcePublisher:
        """Return a ``SandboxResourcePublisher`` bound to the live sandbox.

        Raises ``KeyError`` if the sandbox for *task_id* has not been
        created yet -- callers must call ``create()`` first.
        """
        sandbox = self._sandboxes[task_id]
        return SandboxResourcePublisher(
            sandbox=sandbox,
            run_id=run_id,
            task_execution_id=task_execution_id,
        )

    async def read_report_file(
        self,
        *,
        task_id: UUID,
        workspace_path: str,
        duration_ms: int | None = None,
    ) -> str:
        """Read a report file from the sandbox and emit file-read telemetry."""
        sandbox = self._get_raw_sandbox(task_id)
        content = await sandbox.files.read(workspace_path)
        if isinstance(content, bytes):
            content = content.decode("utf-8")
        await self._emit_wal_entry(
            task_id,
            command=f"files.read {workspace_path}",
            stdout=f"path={workspace_path}\nbytes={len(content.encode('utf-8'))}",
            exit_code=0,
            duration_ms=duration_ms,
        )
        return content

    async def write_report_file(
        self,
        *,
        task_id: UUID,
        workspace_path: str,
        content: str,
        duration_ms: int | None = None,
    ) -> None:
        """Write a report file to the sandbox and emit file-write telemetry."""
        sandbox = self._get_raw_sandbox(task_id)
        await sandbox.files.write(workspace_path, content.encode("utf-8"))
        self.register_created_file(task_id, workspace_path)
        await self._emit_wal_entry(
            task_id,
            command=f"files.write {workspace_path}",
            stdout=f"path={workspace_path}\nbytes={len(content.encode('utf-8'))}",
            exit_code=0,
            duration_ms=duration_ms,
        )
