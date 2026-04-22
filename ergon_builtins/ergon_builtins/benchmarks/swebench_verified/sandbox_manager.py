"""Sandbox manager for the SWE-Bench Verified benchmark.

Per-task setup (cloning the repo at ``base_commit``, creating the venv at
the right Python version, installing deps) is driven by
``swebench.harness.test_spec`` and runs inside
``_install_dependencies`` so it executes exactly once per sandbox_key.
The task payload is fetched from the data layer (``queries.task_executions.
get_task_payload``) rather than piggy-backing on the Inngest event.
"""

import logging
import shlex
from uuid import UUID

from ergon_core.core.providers.sandbox.errors import SandboxSetupError
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager

from ergon_builtins.benchmarks.swebench_verified.criterion import make_test_spec
from ergon_builtins.benchmarks.swebench_verified.sandbox.utils import resolve_template
from ergon_builtins.benchmarks.swebench_verified.sandbox_manager_support import (
    payload_to_swebench_row,
)

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

    async def _create_directory_structure(self, sandbox: AsyncSandbox, sandbox_key: UUID) -> None:
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
            "SWE-Bench dir setup for sandbox_key=%s: mkdir exit=%d",
            sandbox_key,
            result.exit_code,
        )

    async def _install_dependencies(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        """Clone the repo at base_commit and install deps for this SWE-Bench instance.

        Payload is fetched from the data layer (no event-payload leak);
        ``make_test_spec`` produces the canonical setup + install shell
        scripts.  Called exactly once per sandbox by
        ``BaseSandboxManager.create()`` — the early-return at ``create()``
        guards idempotence, so re-entry does not re-run these scripts.
        """
        from ergon_core.core.persistence.queries import queries

        payload = queries.task_executions.get_task_payload(task_id)
        if payload is None:
            raise SandboxSetupError(
                f"No task_payload for task_id={task_id}; prepare step must commit "
                "before sandbox-setup dispatches."
            )
        row = payload_to_swebench_row(payload)
        spec = make_test_spec(row)

        for label, script in (
            ("setup_env", spec.setup_env_script),
            ("install_repo", spec.install_repo_script),
        ):
            logger.info(
                "SWE-Bench _install_dependencies running %s for task_id=%s",
                label,
                task_id,
            )
            r = await sandbox.commands.run(
                f"bash -c {shlex.quote(script)}",
                timeout=1800,
            )
            if r.exit_code != 0:
                tail = (r.stdout or "")[-1000:]
                raise SandboxSetupError(
                    f"swebench {label} failed for task_id={task_id}: exit={r.exit_code} "
                    f"tail={tail!r}"
                )

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
