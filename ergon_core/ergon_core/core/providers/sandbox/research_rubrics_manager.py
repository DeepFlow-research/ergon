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
    ``_install_dependencies`` override.

    Inherits singleton ``__new__`` from ``BaseSandboxManager`` -- do NOT
    re-declare it here.
    """

    type_slug: ClassVar[str] = "researchrubrics"

    # ------------------------------------------------------------------
    # Abstract method implementation
    # ------------------------------------------------------------------

    async def _install_dependencies(
        self,
        sandbox: "AsyncSandbox",  # type: ignore[name-defined]
        task_id: UUID,
    ) -> None:
        """Install research packages and create the workspace layout."""
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
