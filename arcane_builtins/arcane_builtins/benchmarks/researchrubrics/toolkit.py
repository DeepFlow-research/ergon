"""ResearchRubrics toolkit — Exa web-search and report-drafting tool definitions.

Provides Pydantic response models and a ``ResearchRubricsToolkit`` that
produces ``pydantic_ai.tools.Tool`` wrappers for:

- Exa web search / QA / content extraction
- Report draft write / edit / read
- Stakeholder interaction
"""

from __future__ import annotations

from pydantic import BaseModel, Field

try:
    from pydantic_ai.tools import Tool
except ImportError:
    Tool = None  # type: ignore[assignment,misc]


# ── Exa response models ──────────────────────────────────────────────


class ExaSearchResult(BaseModel):
    title: str = Field(description="Page title")
    url: str = Field(description="Page URL")
    summary: str | None = Field(default=None, description="Summary/snippet of the page")
    content: str | None = Field(
        default=None, description="Extracted text content (truncated to 5000 chars)"
    )
    published_date: str | None = Field(default=None, description="Publication date if available")


class ExaSearchResponse(BaseModel):
    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    query: str | None = Field(default=None, description="The search query that was executed")
    results: list[ExaSearchResult] | None = Field(
        default=None, description="List of search results"
    )


class ExaQAResponse(BaseModel):
    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    question: str | None = Field(default=None, description="The question that was asked")
    answer: str | None = Field(default=None, description="The answer extracted from sources")
    sources: list[dict[str, str]] | None = Field(
        default=None, description="List of source dicts with 'url' and 'title' keys"
    )


class ExaGetContentResponse(BaseModel):
    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    url: str | None = Field(default=None, description="URL that was fetched")
    title: str | None = Field(default=None, description="Page title")
    content: str | None = Field(default=None, description="Full extracted text content")
    published_date: str | None = Field(default=None, description="Publication date if available")


# ── Report-draft response models ─────────────────────────────────────


class WriteReportDraftResponse(BaseModel):
    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    file_path: str | None = Field(default=None, description="Path to the written file")
    bytes_written: int | None = Field(default=None, description="Number of bytes written")


class EditReportDraftResponse(BaseModel):
    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    file_path: str | None = Field(default=None, description="Path to the edited file")
    replacements_made: int | None = Field(default=None, description="Number of replacements made")


class ReadReportDraftResponse(BaseModel):
    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    file_path: str | None = Field(default=None, description="Path to the file that was read")
    content: str | None = Field(default=None, description="Content of the file")
    bytes_read: int | None = Field(default=None, description="Number of bytes read")


# ── Toolkit ───────────────────────────────────────────────────────────


class ResearchRubricsToolkit:
    """Produces ``pydantic_ai.tools.Tool`` instances for web research and report drafting.

    All Exa / report-draft tools delegate to a sandbox manager's
    ``run_skill()`` method; the ``ask_stakeholder`` tool delegates to a
    callback supplied by the caller.

    Parameters
    ----------
    sandbox_run_skill:
        Async callable ``(run_id, skill_name, response_model, **kwargs)``
        that executes a skill inside the sandbox.
    ask_stakeholder_fn:
        Async callable ``(question) -> answer`` for stakeholder interaction.
    run_id:
        Opaque run identifier forwarded to ``sandbox_run_skill``.
    """

    def __init__(
        self,
        *,
        sandbox_run_skill,
        ask_stakeholder_fn,
        run_id,
    ) -> None:
        self._run_skill = sandbox_run_skill
        self._ask = ask_stakeholder_fn
        self._run_id = run_id

    def get_tools(self) -> list[Tool]:
        return [
            self._exa_search(),
            self._exa_qa(),
            self._exa_get_content(),
            self._write_report_draft(),
            self._edit_report_draft(),
            self._read_report_draft(),
            self._ask_stakeholder(),
        ]

    # ── Exa tools ─────────────────────────────────────────────────────

    def _exa_search(self) -> Tool:
        async def exa_search_tool(
            query: str,
            num_results: int = 5,
            category: str | None = None,
        ) -> ExaSearchResponse:
            """Search the web using Exa to get ranked search results with content.

            Args:
                query: Search query string
                num_results: Number of results to return (default: 5)
                category: Optional category filter ("news", "academic", "company")
            """
            return await self._run_skill(
                self._run_id,
                "exa_search",
                ExaSearchResponse,
                query=query,
                num_results=num_results,
                category=category,
            )

        return Tool(function=exa_search_tool, takes_ctx=False)

    def _exa_qa(self) -> Tool:
        async def exa_qa_tool(
            question: str,
            num_results: int = 3,
        ) -> ExaQAResponse:
            """Get direct answers to questions from web sources.

            Args:
                question: Question to answer
                num_results: Number of sources to use (default: 3)
            """
            return await self._run_skill(
                self._run_id,
                "exa_qa",
                ExaQAResponse,
                question=question,
                num_results=num_results,
            )

        return Tool(function=exa_qa_tool, takes_ctx=False)

    def _exa_get_content(self) -> Tool:
        async def exa_get_content_tool(url: str) -> ExaGetContentResponse:
            """Extract full content from a URL.

            Args:
                url: URL to extract content from
            """
            return await self._run_skill(
                self._run_id,
                "exa_get_content",
                ExaGetContentResponse,
                url=url,
            )

        return Tool(function=exa_get_content_tool, takes_ctx=False)

    # ── Report-draft tools ────────────────────────────────────────────

    def _write_report_draft(self) -> Tool:
        async def write_report_draft_tool(
            content: str,
            file_path: str = "/workspace/final_output/report.md",
        ) -> WriteReportDraftResponse:
            """Write content to a markdown report file.

            Args:
                content: The markdown content to write (full report)
                file_path: Path to write the file.
                    /workspace/scratchpad/ for drafts (not evaluated).
                    /workspace/final_output/ for final report (default, evaluated).
            """
            return await self._run_skill(
                self._run_id,
                "write_report_draft",
                WriteReportDraftResponse,
                content=content,
                file_path=file_path,
            )

        return Tool(function=write_report_draft_tool, takes_ctx=False)

    def _edit_report_draft(self) -> Tool:
        async def edit_report_draft_tool(
            old_string: str,
            new_string: str,
            file_path: str = "/workspace/final_output/report.md",
        ) -> EditReportDraftResponse:
            """Edit the report using search and replace.

            Args:
                old_string: The text to find and replace
                new_string: The text to replace with
                file_path: Path to the file to edit
            """
            return await self._run_skill(
                self._run_id,
                "edit_report_draft",
                EditReportDraftResponse,
                old_string=old_string,
                new_string=new_string,
                file_path=file_path,
            )

        return Tool(function=edit_report_draft_tool, takes_ctx=False)

    def _read_report_draft(self) -> Tool:
        async def read_report_draft_tool(
            file_path: str = "/workspace/final_output/report.md",
        ) -> ReadReportDraftResponse:
            """Read content from the report file.

            Args:
                file_path: Path to the file to read
            """
            return await self._run_skill(
                self._run_id,
                "read_report_draft",
                ReadReportDraftResponse,
                file_path=file_path,
            )

        return Tool(function=read_report_draft_tool, takes_ctx=False)

    # ── Stakeholder ───────────────────────────────────────────────────

    def _ask_stakeholder(self) -> Tool:
        async def ask_stakeholder_tool(question: str) -> str:
            """Ask the stakeholder a clarifying question about the research task.

            Args:
                question: Your question for the stakeholder
            """
            return await self._ask(question)

        return Tool(function=ask_stakeholder_tool, takes_ctx=False)
