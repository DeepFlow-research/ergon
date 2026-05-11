"""GDPEval ReAct toolkit spec."""

from typing import Any

from ergon_core.api import Sandbox, Task, WorkerContext
from ergon_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandbox
from ergon_builtins.benchmarks.gdpeval.toolkit import GDPEvalToolkit
from ergon_builtins.toolkits.react import ReActToolkit


class _SandboxSkillAdapter:
    """Temporary adapter while GDPEval skills move fully onto Sandbox."""

    def __init__(self, sandbox: GDPEvalSandbox) -> None:
        self._sandbox = sandbox

    async def run_skill(
        self,
        run_id,
        skill_name: str,
        response_model: type,
        **kwargs: Any,  # slopcop: ignore[no-typing-any]
    ) -> Any:  # slopcop: ignore[no-typing-any]
        del run_id
        raise NotImplementedError(
            f"GDPEval skill {skill_name!r} has not been ported from manager-backed "
            f"execution to {type(self._sandbox).__name__} yet. kwargs={sorted(kwargs)} "
            f"response_model={response_model.__name__}"
        )


class GDPEvalReActToolkit(ReActToolkit):
    """Materialize GDPEval document tools against the live sandbox."""

    def build_tools(
        self,
        *,
        task: Task,
        context: WorkerContext,
        sandbox: Sandbox,
    ) -> list[Any]:  # slopcop: ignore[no-typing-any]
        if not isinstance(sandbox, GDPEvalSandbox):
            raise TypeError(f"GDPEvalReActToolkit requires GDPEvalSandbox, got {type(sandbox).__name__}")
        toolkit = GDPEvalToolkit(
            task_id=task.task_id,
            run_id=context.run_id,
            sandbox_manager=_SandboxSkillAdapter(sandbox),
        )
        return list(toolkit.get_tools())
