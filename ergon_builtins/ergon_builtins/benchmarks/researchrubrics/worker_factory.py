"""ResearchRubrics worker factories — one per agentic strategy.

Each factory bundles the ResearchRubrics sandbox, toolkit, and system
prompt with a chosen worker class (ReActWorker today; CoTWorker /
ReflexionWorker future).  Strategies vary independently; the domain
bundle is constant.

v2 callers use ``make_research_worker()`` directly from the benchmark
object graph.
"""

from ergon_builtins.benchmarks.researchrubrics.prompts import RESEARCH_SYSTEM_PROMPT
from ergon_builtins.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from ergon_builtins.benchmarks.researchrubrics.toolkit import ResearchRubricsToolkit

from ergon_builtins.workers.react_worker import ReActWorker

__all__ = [
    "make_research_rubric",
    "make_research_worker",
]


DEFAULT_WORKER_MODEL = "openai:gpt-4o-mini"


def make_research_worker(
    *,
    model: str = DEFAULT_WORKER_MODEL,
    max_iterations: int = 16,
) -> ReActWorker:
    """Return a serializable ReActWorker for ResearchRubrics (v2 authoring shape)."""
    return ReActWorker(
        name="research-runner",
        model=model,
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        max_iterations=max_iterations,
        toolkit=ResearchRubricsToolkit(),
    )


def make_research_rubric() -> ResearchRubricsRubric:
    """Return a serializable ResearchRubricsRubric for use as an inline evaluator.

    The default rubric materialises its judge criteria lazily from the
    task payload (each ``task_payload.rubrics`` entry becomes one
    ``ResearchRubricsJudgeCriterion``), so the rubric body itself stays
    config-only and round-trips through ``task_json``.
    """
    return ResearchRubricsRubric(name="researchrubrics-rubric")
