"""MiniF2F worker factories — one per agentic strategy.

Each factory bundles the MiniF2F sandbox, toolkit, and system
prompt with a chosen worker class (ReActWorker today; CoTWorker /
ReflexionWorker future).  Strategies vary independently; the
domain bundle is constant.

v2 callers use ``make_minif2f_worker()`` directly from the benchmark
object graph.
"""

from ergon_builtins.benchmarks.minif2f.rubric import MiniF2FRubric
from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit
from ergon_builtins.benchmarks.minif2f.prompts import MINIF2F_SYSTEM_PROMPT
from ergon_builtins.workers.react_worker import ReActWorker


DEFAULT_WORKER_MODEL = "openai:gpt-4o-mini"


def make_minif2f_worker(
    *,
    model: str = DEFAULT_WORKER_MODEL,
    max_iterations: int = 30,
) -> ReActWorker:
    """Return a serializable ReActWorker for MiniF2F (v2 authoring shape)."""
    return ReActWorker(
        name="solver",
        model=model,
        system_prompt=MINIF2F_SYSTEM_PROMPT,
        max_iterations=max_iterations,
        toolkit=MiniF2FToolkit(),
    )


def make_minif2f_rubric() -> MiniF2FRubric:
    """Return a serializable MiniF2FRubric for use as an inline evaluator."""
    return MiniF2FRubric(name="minif2f-rubric")
