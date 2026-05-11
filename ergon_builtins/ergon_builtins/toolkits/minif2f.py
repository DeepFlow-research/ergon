"""MiniF2F ReAct toolkit spec."""

from typing import Any
from uuid import UUID

from ergon_core.api import Sandbox, Task, WorkerContext
from ergon_builtins.benchmarks.minif2f.sandbox_manager import MiniF2FSandbox
from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit
from ergon_builtins.toolkits.react import ReActToolkit


def _minif2f_run_skill(sandbox: Any) -> Any:  # slopcop: ignore[no-typing-any]
    async def run_skill(
        _run_id: UUID,
        skill_name: str,
        response_model: type,
        **kwargs: Any,  # slopcop: ignore[no-typing-any]
    ) -> Any:  # slopcop: ignore[no-typing-any]
        if skill_name != "write_lean_file":
            raise ValueError(f"MiniF2F toolkit does not support skill {skill_name!r}")
        file_path = kwargs["file_path"]
        content = kwargs["content"]
        payload = content.encode("utf-8") if isinstance(content, str) else content
        await sandbox.files.write(file_path, payload)
        return response_model(success=True, filename=file_path, bytes_written=len(payload))

    return run_skill


class MiniF2FReActToolkit(ReActToolkit):
    """Materialize MiniF2F tools against the live Lean sandbox."""

    def build_tools(
        self,
        *,
        task: Task,
        context: WorkerContext,
        sandbox: Sandbox,
    ) -> list[Any]:  # slopcop: ignore[no-typing-any]
        del context
        if not isinstance(sandbox, MiniF2FSandbox):
            raise TypeError(f"MiniF2FReActToolkit requires MiniF2FSandbox, got {type(sandbox).__name__}")
        raw_sandbox = sandbox.raw_sandbox
        toolkit = MiniF2FToolkit(
            sandbox=raw_sandbox,
            sandbox_run_skill=_minif2f_run_skill(raw_sandbox),
            run_id=task.task_id,
        )
        return list(toolkit.get_tools())
