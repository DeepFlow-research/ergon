"""Legacy SWE-Bench worker bridge — DELETED IN PR 11.

This file exists solely so the ``"swebench-react"`` registry slug
still resolves for experiments persisted before PR 10a.  Once PR 11
retires the legacy registry fallback chain, delete this entire
file along with ``sandbox_manager.py``.

Do NOT import from this file in new code.  v2 callers use
``workers.make_swebench_worker()``.
"""

import shlex
from collections.abc import AsyncGenerator
from typing import Any, ClassVar, Literal

from pydantic import BaseModel
from pydantic_ai.tools import Tool

from ergon_core.api import Task, WorkerContext, WorkerStreamItem

from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import (
    SWEBenchSandboxManager,
)
from ergon_builtins.workers.baselines.react_prompts import SWEBENCH_SYSTEM_PROMPT
from ergon_builtins.workers.baselines.react_worker import ReActWorker


class _LegacyBashResponse(BaseModel):
    exit_code: int
    stdout: str
    stderr: str


class _LegacyEditorResponse(BaseModel):
    ok: bool
    output: str | None = None
    error: str | None = None


# TODO(PR 11): delete `_legacy_swebench_tools` — only `SWEBenchReactWorker`
# (also scheduled for deletion in PR 11) calls it.  v2 path builds tools
# via `SWEBenchToolkit.tools(sandbox, task)` directly.
def _legacy_swebench_tools(  # noqa: C901
    sandbox: Any,  # slopcop: ignore[no-typing-any]
    *,
    workdir: str = "/workspace/repo",
) -> list[Tool]:
    """Build legacy SWE-Bench tools bound to a raw E2B sandbox handle."""

    async def bash(command: str, timeout_sec: int = 300) -> _LegacyBashResponse:
        """Run a shell command inside the repo workdir."""
        wrapped = f"cd {shlex.quote(workdir)} && {command}"
        result = await sandbox.commands.run(wrapped, timeout=timeout_sec)
        stdout = "" if result.stdout is None else result.stdout
        stderr_value = getattr(result, "stderr", None)  # slopcop: ignore[no-hasattr-getattr]
        stderr = stderr_value if isinstance(stderr_value, str) else ""
        return _LegacyBashResponse(
            exit_code=result.exit_code,
            stdout=stdout,
            stderr=stderr,
        )

    async def str_replace_editor(
        command: Literal["view", "create", "str_replace"],
        path: str,
        file_text: str | None = None,
        old_str: str | None = None,
        new_str: str | None = None,
    ) -> _LegacyEditorResponse:
        """View, create, or edit a file by exact string replacement."""
        abs_path = f"{workdir.rstrip('/')}/{path.lstrip('/')}"
        try:
            if command == "view":
                content = await sandbox.files.read(abs_path)
                return _LegacyEditorResponse(ok=True, output=content)

            if command == "create":
                if file_text is None:
                    return _LegacyEditorResponse(ok=False, error="file_text required for create")
                await sandbox.files.write(abs_path, file_text.encode())
                return _LegacyEditorResponse(ok=True, output=f"created {abs_path}")

            if command == "str_replace":
                if old_str is None or new_str is None:
                    return _LegacyEditorResponse(ok=False, error="old_str and new_str required")
                content = await sandbox.files.read(abs_path)
                occurrences = content.count(old_str)
                if occurrences == 0:
                    return _LegacyEditorResponse(ok=False, error="old_str not found")
                if occurrences > 1:
                    return _LegacyEditorResponse(
                        ok=False,
                        error=f"old_str not unique ({occurrences} matches); add more context",
                    )
                new_content = content.replace(old_str, new_str, 1)
                await sandbox.files.write(abs_path, new_content.encode())
                return _LegacyEditorResponse(ok=True, output=f"edited {abs_path}")

            return _LegacyEditorResponse(ok=False, error=f"unknown command {command!r}")
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            return _LegacyEditorResponse(ok=False, error=str(exc))

    return [
        Tool(function=bash, takes_ctx=False, name="bash"),
        Tool(function=str_replace_editor, takes_ctx=False, name="str_replace_editor"),
    ]


# TODO(PR 11): delete `SWEBenchReactWorker` entirely.  It only exists so the
# `"swebench-react"` slug in the worker registry keeps resolving for
# experiments persisted before PR 10a.  Once PR 11 retires the legacy
# worker fallback chain and `TaskSpec`, this class has no callers.
class SWEBenchReactWorker(ReActWorker):
    """ReAct worker wired to the live SWE-Bench sandbox at execution time.

    Legacy (v1) worker used by the registry and any experiments defined
    before PR 10a.  New experiments use plain ``ReActWorker`` with
    ``toolkit=SWEBenchToolkit()`` embedded in the Task.  This class
    stays alive until PR 11 deletes the registry bridge.
    """

    type_slug: ClassVar[str] = "swebench-react"
    system_prompt: str | None = SWEBENCH_SYSTEM_PROMPT
    max_iterations: int = 50

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        sandbox = SWEBenchSandboxManager().get_sandbox(task.task_id)
        if sandbox is None:
            raise RuntimeError(
                f"SWE-Bench worker requires a live sandbox for task_id={task.task_id}; "
                "SandboxSetupRequest must have completed (including "
                "_install_dependencies) before worker-execute runs."
            )
        self._tools = list(_legacy_swebench_tools(sandbox, workdir="/workspace/repo"))
        async for item in super().execute(task, context=context):
            yield item
