"""SWE-Bench worker factories — one per agentic strategy.

Each factory bundles the SWE-Bench sandbox, toolkit, and system prompt
with a chosen worker class (ReActWorker today; CoTWorker / ReflexionWorker
future).  Strategies vary independently; the domain bundle is constant.

v2 callers use ``make_swebench_worker()`` directly from the benchmark
object graph.
"""

from ergon_builtins.benchmarks.swebench_verified.rubric import SWEBenchRubric
from ergon_builtins.benchmarks.swebench_verified.toolkit import SWEBenchToolkit
from ergon_builtins.workers.baselines.react_prompts import SWEBENCH_SYSTEM_PROMPT
from ergon_builtins.workers.baselines.react_worker import ReActWorker


def make_swebench_worker(
    *,
    model: str = "openai:gpt-4o-mini",
    max_iterations: int = 50,
) -> ReActWorker:
    """Return a serializable ReActWorker for SWE-Bench (v2 authoring shape)."""
    return ReActWorker(
        name="swebench-solver",
        model=model,
        system_prompt=SWEBENCH_SYSTEM_PROMPT,
        max_iterations=max_iterations,
        toolkit=SWEBenchToolkit(),
    )


def make_swebench_rubric() -> SWEBenchRubric:
    """Return a serializable SWEBenchRubric for use as an inline evaluator."""
    return SWEBenchRubric(name="swebench-rubric")
