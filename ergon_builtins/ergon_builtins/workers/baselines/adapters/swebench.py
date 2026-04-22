"""SWE-Bench Verified adapter for :class:`ReActWorker`.

Drives the per-instance harness setup, exposes the bash + str_replace
editor tools via :class:`SWEBenchToolkit`, and after the run extracts
the patch with ``git add -A && git diff HEAD``. The patch is routed
through both ``WorkerOutput.output`` and ``artifacts`` for the same
reason as MiniF2F — the runtime drops ``artifacts`` before scoring.
"""

import logging
import shlex
from typing import Any

from ergon_core.api import BenchmarkTask, WorkerContext, WorkerOutput

from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import (
    SWEBenchSandboxManager,
)
from ergon_builtins.benchmarks.swebench_verified.toolkit import SWEBenchToolkit
from ergon_builtins.workers.baselines.adapters.base import BenchmarkAdapter

logger = logging.getLogger(__name__)

WORKDIR = "/workspace/repo"
SETUP_TIMEOUT_SEC = 1800
PATCH_TIMEOUT_SEC = 60

DEFAULT_SYSTEM_PROMPT = (
    "You are a senior software engineer fixing an issue in a Python repo.\n\n"
    "You have two tools:\n"
    "- bash: run shell commands in the repo workdir.\n"
    "- str_replace_editor: view/create/str_replace files.\n\n"
    "Workflow:\n"
    "1. Read the problem statement and explore the repo layout.\n"
    "2. Locate the relevant files; run failing tests to reproduce.\n"
    "3. Edit code via str_replace_editor; re-run tests until they pass.\n"
    "4. Keep the patch minimal — do not modify test files.\n"
    "The final answer is whatever `git diff HEAD` shows when you stop."
)


def make_test_spec(instance_row: dict[str, Any]) -> Any:  # slopcop: ignore[no-typing-any]
    """Re-exported wrapper so tests can monkeypatch this symbol.

    The underlying ``swebench.harness.test_spec.test_spec.make_test_spec``
    import is deferred to call time to avoid hard-requiring the
    ``swebench`` package at module-import time.
    """
    # reason: lazy import — swebench is heavy and not always installed
    from swebench.harness.test_spec.test_spec import make_test_spec as _mk

    # reason: harness accepts a TypedDict-shaped row at runtime; the SWEbenchInstance
    # annotation in swebench is a typed wrapper the underlying impl does not enforce.
    return _mk(instance_row)  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]


def _payload_to_swebench_row(
    payload: dict[str, Any],  # slopcop: ignore[no-typing-any]
) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
    """Translate a :class:`SWEBenchTaskPayload` dict into a harness row.

    The harness expects UPPER_CASE keys for ``FAIL_TO_PASS`` / ``PASS_TO_PASS``
    and a ``patch`` field (we always pass the empty string since the gold
    patch must never reach the worker).
    """
    return {
        "instance_id": payload["instance_id"],
        "repo": payload["repo"],
        "base_commit": payload["base_commit"],
        "version": payload["version"],
        "problem_statement": payload["problem_statement"],
        "hints_text": payload.get("hints_text", ""),
        "FAIL_TO_PASS": payload["fail_to_pass"],
        "PASS_TO_PASS": payload["pass_to_pass"],
        "environment_setup_commit": payload["environment_setup_commit"],
        "test_patch": payload["test_patch"],
        "patch": "",
    }


class SWEBenchAdapter(BenchmarkAdapter):
    """ReAct adapter for the SWE-Bench Verified benchmark."""

    system_prompt = DEFAULT_SYSTEM_PROMPT
    max_iterations = 50

    def __init__(self, *, workdir: str = WORKDIR) -> None:
        self._sandbox: Any = None  # slopcop: ignore[no-typing-any]
        self._workdir = workdir
        self._patch: str | None = None

    async def on_run_start(
        self,
        task: BenchmarkTask,
        context: WorkerContext,
    ) -> None:
        """Open the sandbox and run ``setup_env`` + ``install_repo`` scripts."""
        manager = SWEBenchSandboxManager()
        sandbox = manager.get_sandbox(context.task_id)
        if sandbox is None:
            raise RuntimeError(
                f"SWE-Bench adapter requires a live sandbox for task_id={context.task_id}; "
                "none is registered on the SWEBenchSandboxManager singleton."
            )
        self._sandbox = sandbox
        await self._run_setup(task)

    async def build_tools(
        self,
        task: BenchmarkTask,
        context: WorkerContext,
    ) -> list[Any]:  # slopcop: ignore[no-typing-any]
        if self._sandbox is None:
            raise RuntimeError("build_tools called before on_run_start opened the sandbox")
        toolkit = SWEBenchToolkit(sandbox=self._sandbox, workdir=self._workdir)
        return list(toolkit.get_tools())

    async def on_run_end(
        self,
        task: BenchmarkTask,
        context: WorkerContext,
    ) -> None:
        # Capture the patch even if the ReAct loop raised or was closed
        # early — without this, evaluation would have no artifact to score
        # against. The sandbox is still alive here; teardown happens after
        # get_output() runs.
        self._patch = await self._extract_patch()
        logger.info(
            "SWE-Bench adapter captured patch: %d bytes",
            len(self._patch or ""),
        )

    def transform_output(
        self,
        context: WorkerContext,
        base: WorkerOutput,
    ) -> WorkerOutput:
        """Route the captured patch through both ``output`` and ``artifacts``.

        The runtime's evaluator dispatch only carries ``execution.output_text``
        forward — ``artifacts`` is dropped in some paths. So we ship the
        patch as the output text itself (mirrors :class:`MiniF2FAdapter`).
        """
        patch = self._patch or ""
        artifacts = dict(base.artifacts) if base.artifacts else {}
        artifacts["patch"] = patch
        return base.model_copy(
            update={
                "output": patch,
                "success": bool(patch.strip()),
                "artifacts": artifacts,
            }
        )

    async def _run_setup(self, task: BenchmarkTask) -> None:
        """Run setup_env + install_repo scripts from the swebench test-spec."""
        row = _payload_to_swebench_row(task.task_payload)
        spec = make_test_spec(row)

        for label, script in (
            ("setup_env", spec.setup_env_script),
            ("install_repo", spec.install_repo_script),
        ):
            logger.info("Running swebench %s for %s", label, task.task_slug)
            result = await self._sandbox.commands.run(
                f"bash -c {shlex.quote(script)}",
                timeout=SETUP_TIMEOUT_SEC,
            )
            if result.exit_code != 0:
                stdout_tail = (result.stdout or "")[-1000:]
                raise RuntimeError(
                    f"swebench {label} failed for {task.task_slug}: exit={result.exit_code} "
                    f"tail={stdout_tail!r}"
                )

    async def _extract_patch(self) -> str:
        """Return ``git diff HEAD`` from the workdir, or ``''`` on failure."""
        if self._sandbox is None:
            return ""
        try:
            result = await self._sandbox.commands.run(
                f"cd {shlex.quote(self._workdir)} && git add -A && git diff HEAD",
                timeout=PATCH_TIMEOUT_SEC,
            )
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            logger.warning("git diff failed: %s", exc)
            return ""
        if result.exit_code != 0:
            logger.warning(
                "git diff exit_code=%d stdout=%s",
                result.exit_code,
                (result.stdout or "")[-500:],
            )
            return ""
        return result.stdout or ""
