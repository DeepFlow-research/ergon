"""SWE-Bench Verified worker factories."""

from uuid import UUID

from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import (
    SWEBenchSandboxManager,
)
from ergon_builtins.benchmarks.swebench_verified.toolkit import SWEBenchToolkit
from ergon_builtins.shared.workers.react_prompts import SWEBENCH_SYSTEM_PROMPT
from ergon_builtins.shared.workers.react_worker import ReActWorker


def swebench_react(
    *,
    name: str,
    model: str | None,
    task_id: UUID,
    sandbox_id: str,
) -> ReActWorker:
    """Registry factory: ReActWorker wired with a live SWE-Bench toolkit."""
    sandbox = SWEBenchSandboxManager().get_sandbox(task_id)
    if sandbox is None:
        raise RuntimeError(
            f"SWE-Bench factory requires a live sandbox for task_id={task_id}; "
            "SandboxSetupRequest must have completed (including "
            "_install_dependencies) before worker-execute runs."
        )
    toolkit = SWEBenchToolkit(sandbox=sandbox, workdir="/workspace/repo")
    return ReActWorker(
        name=name,
        model=model,
        task_id=task_id,
        sandbox_id=sandbox_id,
        tools=list(toolkit.get_tools()),
        system_prompt=SWEBENCH_SYSTEM_PROMPT,
        max_iterations=50,
    )
