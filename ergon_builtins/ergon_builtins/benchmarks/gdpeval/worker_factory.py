"""GDPEval worker factories."""

from collections.abc import AsyncGenerator
from typing import ClassVar

from ergon_core.api import Task, WorkerContext, WorkerStreamItem
from ergon_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandboxManager
from ergon_builtins.benchmarks.gdpeval.toolkit import GDPEvalToolkit
from ergon_builtins.shared.workers.react_worker import ReActWorker

GDPEVAL_SYSTEM_PROMPT = """You are a GDPEval document-processing agent.

Use the provided tools to inspect input documents, transform data, run Python
when useful, and write final artifacts under /workspace/final_output. Keep a
short final answer that names the produced files and any assumptions.
"""


class GDPEvalReactWorker(ReActWorker):
    """ReAct worker wired to the GDPEval document toolkit at execution time."""

    type_slug: ClassVar[str] = "gdpeval-react"
    system_prompt: str | None = GDPEVAL_SYSTEM_PROMPT
    max_iterations: int = 40

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        toolkit = GDPEvalToolkit(
            task_id=task.task_id,
            run_id=context.run_id,
            sandbox_manager=GDPEvalSandboxManager(),
        )
        self._tools = list(toolkit.get_tools())
        async for item in super().execute(task, context=context):
            yield item
