"""GDPEval worker factory helpers."""

from ergon_builtins.shared.workers.react_worker import ReActWorker
from ergon_builtins.toolkits.gdpeval import GDPEvalReActToolkit

GDPEVAL_SYSTEM_PROMPT = """You are a GDPEval document-processing agent.

Use the provided tools to inspect input documents, transform data, run Python
when useful, and write final artifacts under /workspace/final_output. Keep a
short final answer that names the produced files and any assumptions.
"""


def make_gdpeval_react_worker(*, name: str, model: str | None) -> ReActWorker:
    return ReActWorker(
        name=name,
        model=model,
        toolkit=GDPEvalReActToolkit(),
        system_prompt=GDPEVAL_SYSTEM_PROMPT,
        max_iterations=40,
    )
