"""GDPEval worker factories."""

from collections.abc import AsyncGenerator

from ergon_core.api import Sandbox, Task, WorkerContext, WorkerStreamItem
from ergon_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandbox
from ergon_builtins.benchmarks.gdpeval.toolkit import GDPEvalToolkit
from ergon_builtins.shared.workers.react_worker import ReActWorker

GDPEVAL_SYSTEM_PROMPT = """You are a GDPEval document-processing agent.

Use the provided tools to inspect input documents, transform data, run Python
when useful, and write final artifacts under /workspace/final_output. Keep a
short final answer that names the produced files and any assumptions.
"""


class GDPEvalReactWorker(ReActWorker):
    """ReAct worker wired to the GDPEval document toolkit at execution time."""

    type_slug = "gdpeval-react"

    def __init__(self, *, name: str, model: str | None) -> None:
        super().__init__(
            name=name,
            model=model,
            tools=[],
            system_prompt=GDPEVAL_SYSTEM_PROMPT,
            max_iterations=40,
        )

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
        sandbox: Sandbox,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        if not isinstance(sandbox, GDPEvalSandbox):
            raise TypeError(
                f"GDPEvalReactWorker requires GDPEvalSandbox, got {type(sandbox).__name__}"
            )
        toolkit = GDPEvalToolkit(
            task_id=task.task_id,
            run_id=context.run_id,
            sandbox_manager=sandbox.manager,
        )
        self.tools = list(toolkit.get_tools())
        async for item in super().execute(task, context=context, sandbox=sandbox):
            yield item
