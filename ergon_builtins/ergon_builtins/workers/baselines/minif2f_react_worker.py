"""ReAct worker wired to the MiniF2F Lean toolkit.

Thin subclass of :class:`ReActWorker` that fetches the live E2B sandbox
from the :class:`MiniF2FSandboxManager` singleton, builds a
:class:`MiniF2FToolkit` against it, and hands the resulting Tools to the
base class right before ``super().execute()`` iterates the agent.

The toolkit expects a ``sandbox_run_skill`` async callable for
``write_lean_file``. We provide a minimal inline implementation that
writes the file directly via ``sandbox.files.write``. No other skills
are required — search/check/verify tools drive ``sandbox.commands.run``
themselves.
"""

from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from ergon_core.api import BenchmarkTask, WorkerContext
from ergon_core.api.generation import GenerationTurn

from ergon_builtins.benchmarks.minif2f.sandbox_manager import MiniF2FSandboxManager
from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit, WriteLeanResponse
from ergon_builtins.workers.baselines.react_worker import ReActWorker


async def _noop_stakeholder(_question: str) -> str:
    """Stakeholder hint callback — unused in autonomous runs."""
    return (
        "No stakeholder is available in this run. Proceed using only the "
        "Lean tools (write_lean_file, check_lean_file, verify_lean_proof, "
        "search_lemmas)."
    )


def _make_run_skill(sandbox: Any) -> Any:  # slopcop: ignore[no-typing-any]
    """Return a minimal ``sandbox_run_skill`` callable bound to `sandbox`.

    The MiniF2F toolkit only routes ``write_lean_file`` through this
    callback; the other tools use ``sandbox.commands.run`` directly. We
    therefore only need to handle that one skill name.
    """

    async def run_skill(
        _run_id: UUID,
        skill_name: str,
        response_model: type,
        **kwargs: Any,  # slopcop: ignore[no-typing-any]
    ) -> Any:  # slopcop: ignore[no-typing-any]
        if skill_name != "write_lean_file":
            raise ValueError(f"MiniF2FReActWorker does not support skill {skill_name!r}")
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


DEFAULT_SYSTEM_PROMPT = (
    "You are an expert Lean 4 theorem prover. Your task is to produce a "
    "complete, verified proof of the given theorem using Mathlib4.\n\n"
    "Workflow:\n"
    "1. Call write_lean_file to save a candidate proof to "
    "/workspace/scratchpad/draft.lean. Use 'sorry' as a placeholder while "
    "exploring.\n"
    "2. Call check_lean_file to see compilation errors and remaining goals.\n"
    "3. Iterate until the proof has no 'sorry' and no errors.\n"
    "4. Write the final proof to /workspace/final_output/final_solution.lean "
    "and call verify_lean_proof to confirm the Lean kernel accepts it.\n\n"
    "Always import Mathlib at the top. Keep proofs short and use high-level "
    "tactics (ring, linarith, nlinarith, simp, omega) when possible."
)


class MiniF2FReActWorker(ReActWorker):
    """ReAct worker that builds MiniF2F tools against the live sandbox."""

    type_slug = "minif2f-react"

    def __init__(
        self,
        *,
        name: str = "minif2f-react",
        model: str | None = None,
        system_prompt: str | None = None,
        max_iterations: int = 30,
    ) -> None:
        super().__init__(
            name=name,
            model=model,
            tools=[],
            system_prompt=system_prompt or DEFAULT_SYSTEM_PROMPT,
            max_iterations=max_iterations,
        )

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        manager = MiniF2FSandboxManager()
        sandbox = manager.get_sandbox(context.task_id)
        if sandbox is None:
            raise RuntimeError(
                f"MiniF2FReActWorker requires a live sandbox for task_id={context.task_id}; "
                "none is registered on the MiniF2FSandboxManager singleton."
            )

        toolkit = MiniF2FToolkit(
            sandbox=sandbox,
            ask_stakeholder_fn=_noop_stakeholder,
            sandbox_run_skill=_make_run_skill(sandbox),
            run_id=context.run_id,
        )
        self.tools = toolkit.get_tools()

        async for turn in super().execute(task, context=context):
            yield turn


__all__ = [
    "DEFAULT_SYSTEM_PROMPT",
    "MiniF2FReActWorker",
    "WriteLeanResponse",
]
