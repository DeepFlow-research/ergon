"""MiniF2F worker factories."""

from typing import Any
from uuid import UUID

from ergon_builtins.benchmarks.minif2f.sandbox_manager import MiniF2FSandboxManager
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


def minif2f_react(
    *,
    name: str,
    model: str | None,
    task_id: UUID,
    sandbox_id: str,
) -> ReActWorker:
    """Registry factory: ReActWorker wired with a live MiniF2F toolkit."""
    sandbox = MiniF2FSandboxManager().get_sandbox(task_id)
    if sandbox is None:
        raise RuntimeError(
            f"MiniF2F factory requires a live sandbox for task_id={task_id}; "
            "SandboxSetupRequest must have completed before worker-execute runs."
        )
    toolkit = MiniF2FToolkit(
        sandbox=sandbox,
        sandbox_run_skill=_minif2f_run_skill(sandbox),
        run_id=task_id,
    )
    return ReActWorker(
        name=name,
        model=model,
        task_id=task_id,
        sandbox_id=sandbox_id,
        tools=list(toolkit.get_tools()),
        system_prompt=MINIF2F_SYSTEM_PROMPT,
        max_iterations=30,
    )
