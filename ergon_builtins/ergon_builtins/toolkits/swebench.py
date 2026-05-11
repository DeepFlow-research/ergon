"""SWE-Bench ReAct toolkit spec."""

from typing import Any

from ergon_core.api import Sandbox, Task, WorkerContext
from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import SWEBenchSandbox
from ergon_builtins.benchmarks.swebench_verified.toolkit import SWEBenchToolkit
from ergon_builtins.toolkits.react import ReActToolkit


class SWEBenchReActToolkit(ReActToolkit):
    """Materialize SWE-Bench tools against the live repository sandbox."""

    workdir: str = "/workspace/repo"

    def build_tools(
        self,
        *,
        task: Task,
        context: WorkerContext,
        sandbox: Sandbox,
    ) -> list[Any]:  # slopcop: ignore[no-typing-any]
        del task, context
        if not isinstance(sandbox, SWEBenchSandbox):
            raise TypeError(
                f"SWEBenchReActToolkit requires SWEBenchSandbox, got {type(sandbox).__name__}"
            )
        toolkit = SWEBenchToolkit(sandbox=sandbox.raw_sandbox, workdir=self.workdir)
        return list(toolkit.get_tools())
