"""ResearchRubrics toolkit -- six skill handlers for research workers.

Provides ``pydantic_ai.tools.Tool`` wrappers around sandbox skill calls:

- ``exa_search`` -- web search via Exa
- ``exa_qa`` -- direct Q&A via Exa
- ``exa_get_content`` -- URL content extraction via Exa
- ``write_report_draft`` -- write a markdown draft to the sandbox workspace
- ``edit_report_draft`` -- patch an existing draft in the sandbox workspace
- ``read_report_draft`` -- read a draft from the sandbox workspace

The toolkit is constructed with two injected callables (``run_skill`` and
``publisher_sync``) so it stays decoupled from the concrete sandbox manager.
Worker subclasses are responsible for wiring the callables from
``WorkerContext`` at execute time.
"""

from collections.abc import Awaitable, Callable
from typing import cast

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool

from ergon_builtins.benchmarks.researchrubrics.toolkit_types import (
    DocumentResponse,
    QAResponse,
    ReportReadResponse,
    ReportWriteResponse,
    SearchResponse,
)
from ergon_builtins.workers.baselines.tool_budget import (
    AgentToolBudgetDeps,
    AgentToolBudgetExhaustedResult,
)
from ergon_builtins.workers.research_rubrics._run_skill import (
    ExaGetContentSkillRequest,
    ExaQASkillRequest,
    ExaSearchSkillRequest,
    ReportEditSkillRequest,
    ReportReadSkillRequest,
    ReportWriteSkillRequest,
    RunSkillFn,
)

# Callable signature expected by the toolkit:
#   publisher_sync() -> list[RunResourceView]
PublisherSyncFn = Callable[[], Awaitable[list]]  # type: ignore[type-arg]


class ResearchRubricsToolkit:
    """Researcher tool surface for researchrubrics benchmarks.

    Constructed with explicit callables -- not a sandbox-manager reference
    -- so the toolkit stays decoupled from the specific manager class and
    tests can substitute fakes.
    """

    def __init__(
        self,
        *,
        run_skill: RunSkillFn,
        publisher_sync: PublisherSyncFn,
    ) -> None:
        self._run_skill = run_skill
        self._publisher_sync = publisher_sync

    def build_tools(
        self,
    ) -> list:  # type: ignore[type-arg]
        """Return the six research skill tools as ``pydantic_ai.tools.Tool``."""
        if Tool is None:
            raise RuntimeError("pydantic-ai is required to build ResearchRubricsToolkit tools")
        return [
            self._exa_search(),
            self._exa_qa(),
            self._exa_get_content(),
            self._write_report_draft(),
            self._edit_report_draft(),
            self._read_report_draft(),
        ]

    # ------------------------------------------------------------------
    # Exa tools
    # ------------------------------------------------------------------

    def _exa_search(self) -> "Tool":
        async def exa_search(
            ctx: "RunContext[AgentToolBudgetDeps]",
            query: str,
            num_results: int = 5,
        ) -> SearchResponse | AgentToolBudgetExhaustedResult:
            """Search the web via Exa.

            Returns up to ``num_results`` hits with text excerpts (up to
            ~25 000 chars each).  An empty ``results`` list is legitimate
            and distinct from a transport failure.
            """
            tool_budget = ctx.deps.tool_budget
            if tool_budget.increment("exa_search", "other") > tool_budget.max_other_tool_calls:
                return tool_budget.exhausted_result("non-workflow tool budget reached")
            resp = cast(
                SearchResponse | AgentToolBudgetExhaustedResult,
                await self._run_skill(ExaSearchSkillRequest(query=query, num_results=num_results)),
            )
            return cast(SearchResponse, resp)

        return Tool(function=exa_search, takes_ctx=True)

    def _exa_qa(self) -> "Tool":
        async def exa_qa(
            ctx: "RunContext[AgentToolBudgetDeps]",
            question: str,
        ) -> QAResponse | AgentToolBudgetExhaustedResult:
            """Ask Exa a direct question and get a synthesised answer with
            source citations.
            """
            tool_budget = ctx.deps.tool_budget
            if tool_budget.increment("exa_qa", "other") > tool_budget.max_other_tool_calls:
                return tool_budget.exhausted_result("non-workflow tool budget reached")
            resp = cast(QAResponse, await self._run_skill(ExaQASkillRequest(question=question)))
            return resp

        return Tool(function=exa_qa, takes_ctx=True)

    def _exa_get_content(self) -> "Tool":
        async def exa_get_content(
            ctx: "RunContext[AgentToolBudgetDeps]",
            url: str,
        ) -> DocumentResponse | AgentToolBudgetExhaustedResult:
            """Fetch and extract readable text from a URL via Exa.

            Returns the full document text, word count, and publication
            date when available.
            """
            tool_budget = ctx.deps.tool_budget
            if tool_budget.increment("exa_get_content", "other") > tool_budget.max_other_tool_calls:
                return tool_budget.exhausted_result("non-workflow tool budget reached")
            resp = cast(DocumentResponse, await self._run_skill(ExaGetContentSkillRequest(url=url)))
            return resp

        return Tool(function=exa_get_content, takes_ctx=True)

    # ------------------------------------------------------------------
    # Report drafting tools
    # ------------------------------------------------------------------

    def _write_report_draft(self) -> "Tool":
        async def write_report_draft(
            ctx: "RunContext[AgentToolBudgetDeps]",
            relative_path: str,
            content: str,
        ) -> ReportWriteResponse:
            """Write a draft to ``/workspace/<relative_path>``.

            On success the file auto-publishes as a new row in the
            ``run_resources`` log so the manager can observe it via the
            graph toolkit.  Paths that escape ``/workspace/`` are rejected.
            """
            ctx.deps.tool_budget.increment("write_report_draft", "finalization")
            resp = cast(
                ReportWriteResponse,
                await self._run_skill(
                    ReportWriteSkillRequest(relative_path=relative_path, content=content),
                ),
            )
            if resp.kind == "success":
                await self._publisher_sync()
            return resp

        return Tool(function=write_report_draft, takes_ctx=True)

    def _edit_report_draft(self) -> "Tool":
        async def edit_report_draft(
            ctx: "RunContext[AgentToolBudgetDeps]",
            relative_path: str,
            patch: str,
        ) -> ReportWriteResponse:
            """Apply a patch (replacement content) to a draft at
            ``/workspace/<relative_path>``.

            On success the updated file auto-publishes as a new row in
            the ``run_resources`` log.  Paths that escape ``/workspace/``
            are rejected.
            """
            ctx.deps.tool_budget.increment("edit_report_draft", "finalization")
            resp = cast(
                ReportWriteResponse,
                await self._run_skill(
                    ReportEditSkillRequest(relative_path=relative_path, patch=patch),
                ),
            )
            if resp.kind == "success":
                await self._publisher_sync()
            return resp

        return Tool(function=edit_report_draft, takes_ctx=True)

    def _read_report_draft(self) -> "Tool":
        async def read_report_draft(
            ctx: "RunContext[AgentToolBudgetDeps]",
            relative_path: str,
        ) -> ReportReadResponse | AgentToolBudgetExhaustedResult:
            """Read a draft from ``/workspace/<relative_path>``.

            Read-only -- does not trigger a publish.
            """
            tool_budget = ctx.deps.tool_budget
            if (
                tool_budget.increment("read_report_draft", "other")
                > tool_budget.max_other_tool_calls
            ):
                return tool_budget.exhausted_result("non-workflow tool budget reached")
            resp = cast(
                ReportReadResponse,
                await self._run_skill(ReportReadSkillRequest(relative_path=relative_path)),
            )
            return resp

        return Tool(function=read_report_draft, takes_ctx=True)
