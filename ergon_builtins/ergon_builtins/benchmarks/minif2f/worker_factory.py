"""MiniF2F worker factories."""

from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from ergon_core.api import Sandbox, Task, WorkerContext, WorkerStreamItem
from ergon_builtins.benchmarks.minif2f.sandbox_manager import MiniF2FSandbox
from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit
from ergon_builtins.shared.workers.react_prompts import MINIF2F_SYSTEM_PROMPT
from ergon_builtins.shared.workers.react_worker import ReActWorker


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


class MiniF2FReactWorker(ReActWorker):
    """ReAct worker wired to the live MiniF2F sandbox at execution time."""

    type_slug = "minif2f-react"

    def __init__(self, *, name: str, model: str | None) -> None:
        super().__init__(
            name=name,
            model=model,
            tools=[],
            system_prompt=MINIF2F_SYSTEM_PROMPT,
            max_iterations=30,
        )

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
        sandbox: Sandbox,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        if not isinstance(sandbox, MiniF2FSandbox):
            raise TypeError(
                f"MiniF2FReactWorker requires MiniF2FSandbox, got {type(sandbox).__name__}"
            )
        raw_sandbox = sandbox.raw_sandbox
        toolkit = MiniF2FToolkit(
            sandbox=raw_sandbox,
            sandbox_run_skill=_minif2f_run_skill(raw_sandbox),
            run_id=task.task_id,
        )
        self.tools = list(toolkit.get_tools())
        async for item in super().execute(task, context=context, sandbox=sandbox):
            yield item
