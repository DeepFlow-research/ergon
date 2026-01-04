"""MiniF2F-specific sandbox manager with Lean 3 + Mathlib installation."""

from logging import getLogger
from pathlib import Path
from uuid import UUID

from e2b_code_interpreter.code_interpreter_async import AsyncSandbox
from e2b.sandbox.commands.command_handle import CommandExitException

from h_arcane.core.infrastructure.sandbox import BaseSandboxManager, DownloadedFile, DownloadedFiles

logger = getLogger(__name__)

# Lean 3 community version for MiniF2F (which uses Mathlib)
LEAN3_TOOLCHAIN = "leanprover-community/lean:3.51.1"


class MiniF2FSandboxManager(BaseSandboxManager):
    """Sandbox manager for MiniF2F benchmark.

    Installs Lean 3 + Mathlib for formal math proof verification.
    MiniF2F problems require Mathlib imports (e.g., data.real.basic).
    """

    async def _install_dependencies(self, sandbox: AsyncSandbox, run_id: UUID) -> None:
        """Install Lean 3, leanproject, and set up Mathlib project."""
        logger.info(f"Installing Lean 3 + Mathlib (run_id={run_id})...")

        # Step 1: Install elan (Lean version manager)
        if not await self._install_elan(sandbox, run_id):
            raise RuntimeError(f"Failed to install elan for run_id={run_id}")

        # Step 2: Install Lean 3 community toolchain
        if not await self._install_lean3(sandbox, run_id):
            raise RuntimeError(f"Failed to install Lean 3 for run_id={run_id}")

        # Step 3: Install leanproject (Python tool for Mathlib)
        if not await self._install_leanproject(sandbox, run_id):
            raise RuntimeError(f"Failed to install leanproject for run_id={run_id}")

        # Step 4: Set up Mathlib project in /workspace
        if not await self._setup_mathlib_project(sandbox, run_id):
            raise RuntimeError(f"Failed to set up Mathlib project for run_id={run_id}")

        logger.info(f"Successfully installed Lean 3 + Mathlib (run_id={run_id})")

    async def _install_elan(self, sandbox: AsyncSandbox, run_id: UUID) -> bool:
        """Install elan (Lean version manager)."""
        try:
            check_result = await sandbox.commands.run("which elan", timeout=5)
            if check_result.exit_code == 0:
                logger.info(f"elan already installed (run_id={run_id})")
                return True
        except CommandExitException:
            pass  # Not installed

        logger.info(f"Installing elan (run_id={run_id})...")
        try:
            result = await sandbox.commands.run(
                "curl -sSf https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh | sh -s -- -y",
                timeout=120,
            )
            if result.exit_code != 0:
                logger.error(f"elan install failed (run_id={run_id}): {result.stderr}")
                return False
            return True
        except CommandExitException as e:
            logger.error(f"elan install exception (run_id={run_id}): {e}")
            return False

    async def _install_lean3(self, sandbox: AsyncSandbox, run_id: UUID) -> bool:
        """Install Lean 3 community toolchain."""
        logger.info(f"Installing Lean 3 toolchain: {LEAN3_TOOLCHAIN} (run_id={run_id})...")
        try:
            result = await sandbox.commands.run(
                f"export PATH=$HOME/.elan/bin:$PATH && elan toolchain install {LEAN3_TOOLCHAIN}",
                timeout=300,
            )
            if result.exit_code != 0:
                logger.error(f"Lean 3 install failed (run_id={run_id}): {result.stderr}")
                return False

            # Set as default
            await sandbox.commands.run(
                f"export PATH=$HOME/.elan/bin:$PATH && elan default {LEAN3_TOOLCHAIN}",
                timeout=30,
            )
            logger.info(f"Lean 3 installed (run_id={run_id})")
            return True
        except CommandExitException as e:
            logger.error(f"Lean 3 install exception (run_id={run_id}): {e}")
            return False

    async def _install_leanproject(self, sandbox: AsyncSandbox, run_id: UUID) -> bool:
        """Install leanproject via pip."""
        logger.info(f"Installing leanproject (run_id={run_id})...")
        try:
            result = await sandbox.commands.run(
                "pip install mathlibtools",
                timeout=120,
            )
            if result.exit_code != 0:
                logger.error(f"leanproject install failed (run_id={run_id}): {result.stderr}")
                return False
            logger.info(f"leanproject installed (run_id={run_id})")
            return True
        except CommandExitException as e:
            logger.error(f"leanproject install exception (run_id={run_id}): {e}")
            return False

    async def _setup_mathlib_project(self, sandbox: AsyncSandbox, run_id: UUID) -> bool:
        """Set up a Mathlib project in /tools for proof verification.

        NOTE: We install to /tools (not /workspace) so that download_all_outputs()
        doesn't download the thousands of Mathlib .lean files as run outputs.
        """
        logger.info(f"Setting up Mathlib project in /tools (run_id={run_id})...")
        try:
            # Create a new Mathlib project (this downloads Mathlib and its cache)
            # NOTE: /tools directory is created by BaseSandboxManager._create_directory_structure()
            # Using leanproject to create project with Mathlib
            result = await sandbox.commands.run(
                "cd /tools && export PATH=$HOME/.elan/bin:$PATH && leanproject new mathlib_project",
                timeout=600,  # Can take a while to download Mathlib cache
            )
            if result.exit_code != 0:
                logger.error(f"Mathlib project setup failed (run_id={run_id}): {result.stderr}")
                return False

            # Get the Mathlib cache (pre-compiled .olean files)
            logger.info(f"Fetching Mathlib cache (run_id={run_id})...")
            cache_result = await sandbox.commands.run(
                "cd /tools/mathlib_project && export PATH=$HOME/.elan/bin:$PATH && "
                "leanproject get-mathlib-cache",
                timeout=600,
            )
            if cache_result.exit_code != 0:
                logger.warning(
                    f"Mathlib cache fetch failed (run_id={run_id}), "
                    f"proofs may be slower: {cache_result.stderr}"
                )
                # Don't fail - can still work without cache, just slower

            logger.info(f"Mathlib project ready (run_id={run_id})")
            return True
        except CommandExitException as e:
            logger.error(f"Mathlib project setup exception (run_id={run_id}): {e}")
            return False

    async def _verify_setup(self, sandbox: AsyncSandbox, run_id: UUID) -> None:
        """Verify Lean 3 + Mathlib is accessible and working."""
        logger.info(f"Verifying Lean 3 + Mathlib setup (run_id={run_id})...")

        try:
            # Verify Lean version
            result = await sandbox.commands.run(
                "export PATH=$HOME/.elan/bin:$PATH && lean --version", timeout=10
            )
            if result.exit_code != 0:
                raise RuntimeError(
                    f"Lean verification failed (run_id={run_id}): "
                    f"exit_code={result.exit_code}, stderr={result.stderr}"
                )
            logger.info(f"Lean setup verified: {result.stdout.strip()} (run_id={run_id})")

            # Verify Mathlib project exists
            proj_check = await sandbox.commands.run("test -d /tools/mathlib_project", timeout=5)
            if proj_check.exit_code != 0:
                raise RuntimeError(
                    f"Mathlib project not found at /tools/mathlib_project (run_id={run_id})"
                )
            logger.info(f"Mathlib project verified (run_id={run_id})")

        except CommandExitException as e:
            raise RuntimeError(f"Setup verification failed (run_id={run_id}): {e}") from e

    async def download_all_outputs(self, run_id: UUID, output_dir: Path) -> DownloadedFiles:
        """Download outputs including Lean proof files from Mathlib project src.

        Overrides base implementation to grab the agent's final solution from
        /tools/mathlib_project/src/. Only downloads final_solution.lean (the required
        submission file) and any other non-internal .lean files the agent created.
        This avoids downloading the thousands of Mathlib library files in _target/.
        """
        # Get standard /workspace outputs first
        downloaded = await super().download_all_outputs(run_id, output_dir)

        # Download .lean files from the Mathlib project src directory
        # Priority: final_solution.lean (required), then other agent files (not internal _*)
        try:
            lean_src_files = await self.list_files(run_id, "/tools/mathlib_project/src")
            for file_path in lean_src_files:
                filename = Path(file_path).name
                # Download final_solution.lean and any non-internal agent files
                # Skip internal files like _search_query.lean and verify.lean (evaluator's)
                if (
                    filename.endswith(".lean")
                    and not filename.startswith("_")
                    and filename != "verify.lean"
                ):
                    try:
                        content = await self.download_file(run_id, file_path)
                        local_path = output_dir / filename
                        local_path.write_bytes(content)
                        downloaded.files.append(
                            DownloadedFile(
                                sandbox_path=file_path,
                                local_path=str(local_path),
                                size_bytes=len(content),
                            )
                        )
                    except RuntimeError as e:
                        logger.warning(f"Failed to download {file_path}: {e}")
                        continue
        except Exception as e:
            error_msg = str(e).lower()
            if "timeout" in error_msg or "sandbox was not found" in error_msg:
                logger.warning(
                    f"Sandbox timeout/not found when downloading Lean files for run_id={run_id}: {e}"
                )
            else:
                logger.warning(f"Failed to download Lean files from Mathlib project: {e}")

        return downloaded
