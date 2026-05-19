"""GDPEval worker factories — one per agentic strategy.

Each factory bundles the GDPEval sandbox, toolkit, and system prompt
with a chosen worker class (ReActWorker today; CoTWorker / ReflexionWorker
future).  Strategies vary independently; the domain bundle is constant.

PR 11 removed the legacy registry bridge. v2 callers use
``make_gdpeval_worker()`` directly from the benchmark object graph.
"""

from ergon_builtins.benchmarks.gdpeval.rubric import StagedRubric
from ergon_builtins.benchmarks.gdpeval.toolkit import GDPEvalToolkit

from ergon_builtins.shared.workers.react_worker import ReActWorker

__all__ = [
    "make_gdpeval_rubric",
    "make_gdpeval_worker",
]


_GDPEVAL_SYSTEM_PROMPT = """You are a GDPEval document-processing agent.

Use the provided tools to inspect input documents, transform data, run Python
when useful, and write final artifacts under /workspace/final_output. Keep a
short final answer that names the produced files and any assumptions.
"""


def make_gdpeval_worker(
    *,
    model: str = "openai:gpt-4o-mini",
    max_iterations: int = 40,
) -> ReActWorker:
    """Return a serializable ReActWorker for GDPEval (v2 authoring shape)."""
    return ReActWorker(
        name="gdpeval-runner",
        model=model,
        system_prompt=_GDPEVAL_SYSTEM_PROMPT,
        max_iterations=max_iterations,
        toolkit=GDPEvalToolkit(),
    )


def make_gdpeval_rubric() -> StagedRubric:
    """Return a serializable GDPEval ``StagedRubric`` for inline evaluation.

    The default rubric is empty-staged; callers can pass a pre-configured
    ``StagedRubric`` directly to ``GDPEvalBenchmark(evaluator_factory=...)``
    when bespoke stage configuration is needed.
    """
    return StagedRubric(
        name="gdpeval-staged-rubric",
        category_name="default",
        max_total_score=1.0,
    )
