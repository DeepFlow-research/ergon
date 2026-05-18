"""ResearchRubrics worker factories — one per agentic strategy.

Each factory bundles the ResearchRubrics sandbox, toolkit, and system
prompt with a chosen worker class (ReActWorker today; CoTWorker /
ReflexionWorker future).  Strategies vary independently; the domain
bundle is constant.

Legacy registry bridges (``ResearchRubricsResearcherWorker`` and
``ResearchRubricsWorkflowCliReActWorker``) are re-exported below so the
existing ``researchrubrics-researcher`` and
``researchrubrics-workflow-cli-react`` registry slugs keep resolving for
experiments persisted before PR 10b.  PR 11 drops these re-exports.
"""

from ergon_builtins.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from ergon_builtins.benchmarks.researchrubrics.toolkit import ResearchRubricsToolkit

# TODO(PR 11): drop these re-exports along with the
# ``researchrubrics-researcher`` / ``researchrubrics-workflow-cli-react``
# registry slugs.  v2 callers use ``make_research_worker()`` directly.
from ergon_builtins.workers.research_rubrics.researcher_worker import (
    ResearchRubricsResearcherWorker,
)
from ergon_builtins.workers.research_rubrics.workflow_cli_react_worker import (
    ResearchRubricsWorkflowCliReActWorker,
)
from ergon_builtins.workers.baselines.react_worker import ReActWorker

__all__ = [
    "ResearchRubricsResearcherWorker",
    "ResearchRubricsWorkflowCliReActWorker",
    "make_research_rubric",
    "make_research_worker",
]


_RESEARCH_SYSTEM_PROMPT = (
    "Role: You are a focused ResearchRubrics research agent.\n\n"
    "Goal: Produce `/workspace/final_output/report.md` with a concise, "
    "well-sourced answer to your scoped task. Include a # Findings section "
    "and a ## Sources section with citations.\n\n"
    "Tools:\n"
    "- `bash`: run shell commands inside the research workspace.\n"
    "- `write_report` / `read_report`: create and inspect markdown report "
    "files under `/workspace/`.\n\n"
    "Stop rules: Use the minimum evidence sufficient to answer correctly, "
    "then write the report and stop."
)


def make_research_worker(
    *,
    model: str = "openai:gpt-4o-mini",
    max_iterations: int = 16,
) -> ReActWorker:
    """Return a serializable ReActWorker for ResearchRubrics (v2 authoring shape)."""
    return ReActWorker(
        name="research-runner",
        model=model,
        system_prompt=_RESEARCH_SYSTEM_PROMPT,
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
