"""Sandbox manager for smoke testing - uses real E2B sandboxes for evaluation."""

from logging import getLogger
from uuid import UUID

from e2b_code_interpreter.code_interpreter_async import AsyncSandbox

from h_arcane.core._internal.infrastructure.sandbox import BaseSandboxManager

logger = getLogger(__name__)


class SmokeTestSandboxManager(BaseSandboxManager):
    """Real sandbox manager for smoke testing.

    Uses actual E2B sandboxes to support code rule evaluation in the
    evaluation pipeline. No extra dependencies are installed beyond
    the E2B default Python environment.
    """

    async def _install_dependencies(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        """No extra dependencies needed for smoke test.

        The E2B default environment has numpy, pandas, etc. which is
        sufficient for smoke test code rules.
        """
        logger.info(f"SmokeTestSandboxManager: no extra dependencies needed (task_id={task_id})")
