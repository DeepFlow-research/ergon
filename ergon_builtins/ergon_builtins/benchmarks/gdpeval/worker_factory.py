"""GDPEval worker factories."""

from uuid import UUID

from ergon_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandboxManager
from ergon_builtins.benchmarks.gdpeval.toolkit import GDPEvalToolkit
from ergon_builtins.shared.workers.react_worker import ReActWorker

GDPEVAL_SYSTEM_PROMPT = """You are a GDPEval document-processing agent.

Use the provided tools to inspect input documents, transform data, run Python
when useful, and write final artifacts under /workspace/final_output. Keep a
short final answer that names the produced files and any assumptions.
"""


def gdpeval_react(
    *,
    name: str,
    model: str | None,
    task_id: UUID,
    sandbox_id: str,
) -> ReActWorker:
    """Registry factory: ReActWorker wired with the GDPEval document toolkit."""
    toolkit = GDPEvalToolkit(
        task_id=task_id,
        run_id=task_id,
        sandbox_manager=GDPEvalSandboxManager(),
    )
    return ReActWorker(
        name=name,
        model=model,
        task_id=task_id,
        sandbox_id=sandbox_id,
        tools=list(toolkit.get_tools()),
        system_prompt=GDPEVAL_SYSTEM_PROMPT,
        max_iterations=40,
    )
