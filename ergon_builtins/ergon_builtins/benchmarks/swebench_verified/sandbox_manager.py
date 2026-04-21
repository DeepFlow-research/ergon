"""Sandbox manager for the SWE-Bench Verified benchmark.

Per-task setup (cloning the repo at ``base_commit``, creating the venv at
the right Python version, installing deps) is driven by
``swebench.harness.test_spec`` and is performed by the worker at task
start, not here.  This manager only provisions the E2B sandbox from the
pre-built template.
"""

import logging
from uuid import UUID

from ergon_core.core.providers.sandbox.manager import BaseSandboxManager

from ergon_builtins.benchmarks.swebench_verified.sandbox.utils import resolve_template

try:
    from e2b_code_interpreter import AsyncSandbox  # type: ignore[import-untyped]
except ImportError:
    AsyncSandbox = object  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


class SWEBenchSandboxManager(BaseSandboxManager):
    """Singleton manager that hands out E2B sandboxes built from ergon-swebench-v1.

    Resolves its template on first instantiation: prefers the pinned
    template_id written by ``ergon benchmark setup swebench-verified``,
    falling back to the mutable template name ``ergon-swebench-v1``.
    """

    def __init__(self) -> None:
        super().__init__()
        # Instance-level override of BaseSandboxManager.template (ClassVar).
        # Resolved at construction time so registry changes take effect on
        # the next manager re-instantiation.
        self.template = resolve_template()

    async def _create_directory_structure(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        """Ensure workspace dirs exist and are writable by the sandbox user.

        The base class uses ``sandbox.run_code`` (the E2B code-interpreter
        Jupyter endpoint) which our bare-Dockerfile template does not
        expose.  We use plain shell commands instead.
        """
        result = await sandbox.commands.run(
            "mkdir -p /tmp/swebench_probe /workspace/scratchpad "
            "/workspace/final_output /inputs 2>/dev/null || true",
            timeout=30,
        )
        logger.debug(
            "SWE-Bench dir setup for task_id=%s: mkdir exit=%d",
            task_id,
            result.exit_code,
        )

    async def _install_dependencies(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        # Template is pre-built; per-task repo clone / venv / dep install is
        # driven by the worker using swebench.harness.test_spec scripts.
        pass

    async def _verify_setup(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        logger.info("Verifying SWE-Bench toolchain in sandbox (task_id=%s) …", task_id)
        result = await sandbox.commands.run("git --version && uv --version")
        if result.exit_code != 0:
            stdout = result.stdout or "(no stdout)"
            stderr = result.stderr or "(no stderr)"
            raise RuntimeError(
                f"SWE-Bench sandbox smoke check failed for task_id={task_id}. "
                f"`git --version && uv --version` exit={result.exit_code}. "
                f"stdout={stdout!r} stderr={stderr!r}"
            )
        logger.info(
            "SWE-Bench sandbox verified (task_id=%s): %s",
            task_id,
            (result.stdout or "(no version output)").strip(),
        )
