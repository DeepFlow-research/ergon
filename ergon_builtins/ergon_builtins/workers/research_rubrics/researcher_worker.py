"""ResearchRubrics researcher worker.

Builds the 9-tool researcher inventory (Exa + report drafting + graph
observability) at execute time from WorkerContext, then delegates to
ReActWorker.execute().
"""

from collections.abc import AsyncGenerator
from typing import ClassVar

from ergon_core.api.generation import GenerationTurn
from ergon_core.api.run_resource import RunResourceView
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.worker_context import WorkerContext
from ergon_core.core.providers.sandbox.research_rubrics_manager import (
    ResearchRubricsSandboxManager,
)

from ergon_builtins.tools.graph_toolkit import ResearchGraphToolkit
from ergon_builtins.tools.research_rubrics_toolkit import (
    ResearchRubricsToolkit,
)
from ergon_builtins.workers.baselines.react_worker import ReActWorker
from ergon_builtins.workers.research_rubrics._run_skill import (
    make_run_skill,
)

_RESEARCHER_SYSTEM_PROMPT = (
    "You are a research agent. Your job is to investigate a research question "
    "using web search and produce a well-sourced report.\n\n"
    "You have access to:\n"
    "- exa_search: Search the web for relevant sources\n"
    "- exa_qa: Ask Exa a direct question\n"
    "- exa_get_content: Extract full text from a URL\n"
    "- write_report_draft: Write a markdown report draft\n"
    "- edit_report_draft: Edit an existing draft\n"
    "- read_report_draft: Read a draft file\n"
    "- Resource discovery tools to observe peer outputs\n\n"
    "Write your final report to 'final_output/report.md' using write_report_draft. "
    "Include a # Findings section and a ## Sources section with citations."
)


class ResearchRubricsResearcherWorker(ReActWorker):
    """Researcher worker for researchrubrics benchmarks.

    Builds the 9-tool researcher inventory (Exa + report drafting + graph
    observability) at execute time from WorkerContext.  The run_skill
    callable delegates to a pydantic-ai Agent for structured output.
    """

    type_slug: ClassVar[str] = "researchrubrics-researcher"

    def __init__(
        self,
        *,
        name: str,
        model: str | None = None,
    ) -> None:
        super().__init__(
            name=name,
            model=model,
            tools=[],
            system_prompt=_RESEARCHER_SYSTEM_PROMPT,
            max_iterations=25,
        )

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        manager = ResearchRubricsSandboxManager()

        run_skill = make_run_skill(model=self.model)

        async def publisher_sync() -> list[RunResourceView]:
            publisher = manager.publisher_for(
                task_id=context.task_id,
                run_id=context.run_id,
                task_execution_id=context.execution_id,
            )
            return await publisher.sync()

        rr_toolkit = ResearchRubricsToolkit(
            run_skill=run_skill,
            publisher_sync=publisher_sync,
        )
        rr_tools = rr_toolkit.build_tools()

        graph_toolkit = ResearchGraphToolkit(
            run_id=context.run_id,
            task_execution_id=context.execution_id,
        )
        graph_tools = graph_toolkit.build_tools()

        self.tools = [*rr_tools, *graph_tools]

        async for turn in super().execute(task, context=context):
            yield turn
