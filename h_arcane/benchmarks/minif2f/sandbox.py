"""MiniF2F-specific sandbox manager with Lean toolchain installation."""

from logging import getLogger
from uuid import UUID

from e2b_code_interpreter.code_interpreter_async import AsyncSandbox
from e2b.sandbox.commands.command_handle import CommandExitException

from h_arcane.core.infrastructure.sandbox import BaseSandboxManager

logger = getLogger(__name__)


class MiniF2FSandboxManager(BaseSandboxManager):
    """Sandbox manager for MiniF2F benchmark.

    Installs the Lean theorem prover via elan (Lean version manager).
    This is needed for proof verification during both worker execution
    and evaluation.
    """

    async def _install_dependencies(self, sandbox: AsyncSandbox, run_id: UUID) -> None:
        """Install Lean theorem prover via elan."""
        logger.info(f"Installing Lean toolchain (run_id={run_id})...")

        installed = await self._ensure_lean_installed(sandbox, run_id)
        if not installed:
            raise RuntimeError(f"Failed to install Lean toolchain for run_id={run_id}")

        logger.info(f"Successfully installed Lean toolchain (run_id={run_id})")

    async def _ensure_lean_installed(self, sandbox: AsyncSandbox, run_id: UUID) -> bool:
        """Install Lean on-demand. Returns True if installed successfully.

        Args:
            sandbox: E2B sandbox instance
            run_id: UUID of the run (for logging)

        Returns:
            True if Lean is installed successfully, False otherwise
        """
        # Check if elan exists - handle CommandExitException for non-zero exit
        elan_exists = False
        try:
            check_result = await sandbox.commands.run("which elan", timeout=5)
            elan_exists = check_result.exit_code == 0
        except CommandExitException:
            # "which" returned non-zero, elan not installed
            elan_exists = False

        if elan_exists:
            # Verify Lean is actually available
            try:
                lean_check = await sandbox.commands.run(
                    "export PATH=$HOME/.elan/bin:$PATH && lean --version", timeout=10
                )
                if lean_check.exit_code == 0:
                    logger.info(f"Lean already installed (run_id={run_id})")
                    return True
            except CommandExitException:
                pass  # Lean not working, need to reinstall

        # Install elan (Lean version manager)
        logger.info(f"Installing elan (Lean version manager) (run_id={run_id})...")
        try:
            install_result = await sandbox.commands.run(
                "curl -sSf https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh | sh -s -- -y",
                timeout=120,
            )
            if install_result.exit_code != 0:
                logger.error(
                    f"Failed to install elan (run_id={run_id}): "
                    f"exit_code={install_result.exit_code}, stderr={install_result.stderr}"
                )
                return False
        except CommandExitException as e:
            logger.error(f"elan installation failed with exception (run_id={run_id}): {e}")
            return False

        # Install stable Lean toolchain
        logger.info(
            f"Installing Lean stable toolchain (run_id={run_id})... (this may take a few minutes)"
        )
        try:
            toolchain_result = await sandbox.commands.run(
                "export PATH=$HOME/.elan/bin:$PATH && elan toolchain install stable",
                timeout=300,  # Can take a while
            )
            if toolchain_result.exit_code != 0:
                logger.error(
                    f"Failed to install Lean toolchain (run_id={run_id}): "
                    f"exit_code={toolchain_result.exit_code}, stderr={toolchain_result.stderr}"
                )
                return False
        except CommandExitException as e:
            logger.error(
                f"Lean toolchain installation failed with exception (run_id={run_id}): {e}"
            )
            return False

        # Verify installation
        try:
            verify_result = await sandbox.commands.run(
                "export PATH=$HOME/.elan/bin:$PATH && lean --version", timeout=10
            )
            success = verify_result.exit_code == 0
            if success:
                logger.info(f"Lean installation verified (run_id={run_id})")
            else:
                logger.error(f"Lean verification failed (run_id={run_id})")
            return success
        except CommandExitException as e:
            logger.error(f"Lean verification failed with exception (run_id={run_id}): {e}")
            return False

    async def _verify_setup(self, sandbox: AsyncSandbox, run_id: UUID) -> None:
        """Verify Lean is accessible and working."""
        logger.info(f"Verifying Lean setup (run_id={run_id})...")

        try:
            result = await sandbox.commands.run(
                "export PATH=$HOME/.elan/bin:$PATH && lean --version", timeout=10
            )
            if result.exit_code != 0:
                raise RuntimeError(
                    f"Lean verification failed (run_id={run_id}): "
                    f"exit_code={result.exit_code}, stderr={result.stderr}"
                )
            logger.info(f"Lean setup verified: {result.stdout.strip()} (run_id={run_id})")
        except CommandExitException as e:
            raise RuntimeError(f"Lean verification failed (run_id={run_id}): {e}") from e
