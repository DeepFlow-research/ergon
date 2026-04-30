"""SWE-Bench Verified worker factories."""

from collections.abc import AsyncGenerator

from ergon_core.api import Task, WorkerContext, WorkerStreamItem
from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import (
    SWEBenchSandboxManager,
)
from ergon_builtins.benchmarks.swebench_verified.toolkit import SWEBenchToolkit
from ergon_builtins.shared.workers.react_prompts import SWEBENCH_SYSTEM_PROMPT
from ergon_builtins.shared.workers.react_worker import ReActWorker


class SWEBenchReactWorker(ReActWorker):
    """ReAct worker wired to the live SWE-Bench sandbox at execution time."""

    type_slug = "swebench-react"

    def __init__(self, *, name: str, model: str | None) -> None:
        super().__init__(
            name=name,
            model=model,
            tools=[],
            system_prompt=SWEBENCH_SYSTEM_PROMPT,
            max_iterations=50,
        )

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
        toolkit = SWEBenchToolkit(sandbox=sandbox, workdir="/workspace/repo")
        self.tools = list(toolkit.get_tools())
        async for item in super().execute(task, context=context):
            yield item
