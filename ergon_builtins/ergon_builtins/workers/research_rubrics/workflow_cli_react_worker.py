"""ResearchRubrics workflow ReAct worker factory."""

from ergon_builtins.toolkits.researchrubrics import ResearchRubricsWorkflowToolkit
from ergon_builtins.workers.baselines.react_worker import ReActWorker

WORKFLOW_REACT_PROMPT = (
    "Role: You are a recursive ResearchRubrics research agent with workflow access.\n\n"
    "Goal: Produce `final_output/report.md` with a well-sourced answer to the task. "
    "Include a # Findings section and a ## Sources section with citations.\n\n"
    "Use workflow context before deep research, create subtasks only for genuinely "
    "parallel evidence-gathering or checking work, and write `final_output/report.md` "
    "once the available evidence can answer the task. If any tool returns "
    "TOOL_BUDGET_EXHAUSTED, stop polling/searching and produce the best possible "
    "final output from current context/resources."
)


def make_researchrubrics_workflow_react_worker(
    *,
    name: str,
    model: str | None,
) -> ReActWorker:
    return ReActWorker(
        name=name,
        model=model,
        toolkit=ResearchRubricsWorkflowToolkit(model=model),
        system_prompt=WORKFLOW_REACT_PROMPT,
        max_iterations=60,
    )
