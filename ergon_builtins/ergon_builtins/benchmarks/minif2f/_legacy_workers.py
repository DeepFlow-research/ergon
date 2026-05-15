"""Legacy MiniF2F worker bridge — DELETED IN PR 11.

This file exists solely so the ``"minif2f-react"`` registry slug
still resolves for experiments persisted before PR 6.  Once PR 11
retires the legacy registry fallback chain, delete this entire
file along with ``sandbox_manager.py``.

Do NOT import from this file in new code.  v2 callers use
``workers.make_minif2f_worker()``.
"""

from collections.abc import AsyncGenerator
from typing import Any, ClassVar
from uuid import UUID

from ergon_core.api import Task, WorkerContext, WorkerStreamItem

from ergon_builtins.benchmarks.minif2f._legacy_toolkit import (
    MiniF2FToolkit as _LegacyMiniF2FToolkit,
)
from ergon_builtins.benchmarks.minif2f.sandbox_manager import MiniF2FSandboxManager
from ergon_builtins.workers.baselines.react_prompts import MINIF2F_SYSTEM_PROMPT
from ergon_builtins.workers.baselines.react_worker import ReActWorker


# TODO(PR 11): delete `_minif2f_run_skill` — only `MiniF2FReactWorker` (also
# scheduled for deletion in PR 11) calls it.  v2 path builds tools via
# `MiniF2FToolkit.tools(sandbox, task)` directly.
def _minif2f_run_skill(sandbox: Any) -> Any:  # slopcop: ignore[no-typing-any]
    """Return the ``write_lean_file`` run_skill callback bound to ``sandbox``."""

    async def run_skill(
        _run_id: UUID,
        skill_name: str,
        response_model: type,
        **kwargs: Any,  # slopcop: ignore[no-typing-any]
    ) -> Any:  # slopcop: ignore[no-typing-any]
        if skill_name != "write_lean_file":
            raise ValueError(f"MiniF2F factory does not support skill {skill_name!r}")
        file_path = kwargs["file_path"]
        content = kwargs["content"]
        payload = content.encode("utf-8") if isinstance(content, str) else content
        await sandbox.files.write(file_path, payload)
        return response_model(
            success=True,
            filename=file_path,
            bytes_written=len(payload),
        )

    return run_skill


# TODO(PR 11): delete `MiniF2FReactWorker` entirely.  It only exists so the
# `"minif2f-react"` slug in the worker registry keeps resolving for
# experiments persisted before PR 6.  Once PR 11 retires the legacy worker
# fallback chain and `TaskSpec`, this class has no callers.
class MiniF2FReactWorker(ReActWorker):
    """ReAct worker wired to the live MiniF2F sandbox at execution time.

    Legacy (v1) worker used by the registry and any experiments defined
    before PR 6.  New experiments use plain ``ReActWorker`` with
    ``toolkit=MiniF2FToolkit()`` embedded in the Task.  This class
    stays alive until PR 11 deletes the registry bridge.
    """

    type_slug: ClassVar[str] = "minif2f-react"
    system_prompt: str | None = MINIF2F_SYSTEM_PROMPT
    max_iterations: int = 30

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        sandbox = MiniF2FSandboxManager().get_sandbox(task.task_id)
        if sandbox is None:
            raise RuntimeError(
                f"MiniF2F worker requires a live sandbox for task_id={task.task_id}; "
                "SandboxSetupRequest must have completed before worker-execute runs."
            )
        legacy_toolkit = _LegacyMiniF2FToolkit(
            sandbox=sandbox,
            sandbox_run_skill=_minif2f_run_skill(sandbox),
            run_id=task.task_id,
        )
        self._tools = list(legacy_toolkit.get_tools())
        async for item in super().execute(task, context=context):
            yield item
