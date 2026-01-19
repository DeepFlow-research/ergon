"""ResearchRubrics sandbox manager.

ResearchRubrics uses Exa API for web research. Skills run in the E2B sandbox
with the EXA_API_KEY environment variable passed at sandbox creation.
"""

from logging import getLogger
from uuid import UUID

from e2b_code_interpreter.code_interpreter_async import AsyncSandbox

from h_arcane.core._internal.infrastructure.sandbox import BaseSandboxManager

logger = getLogger(__name__)


class ResearchRubricsSandboxManager(BaseSandboxManager):
    """Sandbox manager for ResearchRubrics benchmark.

    Installs exa_py for web research capabilities in the sandbox.
    EXA_API_KEY is passed via environment variables at sandbox creation.
    """

    async def _install_dependencies(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        """Install exa_py for Exa API access in sandbox.

        Args:
            sandbox: E2B sandbox instance
            task_id: UUID of the task (for logging)
        """
        logger.info(f"Installing exa_py for ResearchRubrics (task_id={task_id})")

        # Install exa_py for Exa API access
        result = await sandbox.commands.run("pip install exa_py --quiet")
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to install exa_py: {result.stderr}")

        logger.info(f"ResearchRubrics dependencies installed (task_id={task_id})")

    async def _verify_setup(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        """Verify exa_py is importable.

        Args:
            sandbox: E2B sandbox instance
            task_id: UUID of the task (for logging)
        """
        verify_code = """
import exa_py
print("exa_py imported successfully")
"""
        result = await sandbox.run_code(verify_code, language="python")
        if result.error:
            raise RuntimeError(f"Failed to verify exa_py import: {result.error}")

        logger.info(f"ResearchRubrics sandbox setup verified (task_id={task_id})")
