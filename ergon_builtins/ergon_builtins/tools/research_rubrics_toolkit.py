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
from typing import TypeVar

try:
    from pydantic_ai.tools import Tool
except ImportError:  # pragma: no cover -- defensive
    Tool = None  # type: ignore[misc,assignment]

from ergon_builtins.benchmarks.researchrubrics.toolkit_types import (
    DocumentResponse,
    QAResponse,
    ReportReadResponse,
    ReportWriteResponse,
    SearchResponse,
)

_T = TypeVar("_T")

# Callable signatures expected by the toolkit:
#   run_skill(skill_name: str, response_model: type[T], **kwargs) -> T
#   publisher_sync() -> list[RunResourceView]
RunSkillFn = Callable[..., Awaitable[_T]]
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
        run_skill: RunSkillFn,  # type: ignore[type-arg]
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
            query: str,
            num_results: int = 5,
        ) -> SearchResponse:
            """Search the web via Exa.

            Returns up to ``num_results`` hits with text excerpts (up to
            ~25 000 chars each).  An empty ``results`` list is legitimate
            and distinct from a transport failure.
            """
            return await self._run_skill(
                "exa_search",
                SearchResponse,
                query=query,
                num_results=num_results,
            )

        return Tool(function=exa_search, takes_ctx=False)

    def _exa_qa(self) -> "Tool":
        async def exa_qa(question: str) -> QAResponse:
            """Ask Exa a direct question and get a synthesised answer with
            source citations.
            """
            return await self._run_skill(
                "exa_qa",
                QAResponse,
                question=question,
            )

        return Tool(function=exa_qa, takes_ctx=False)

    def _exa_get_content(self) -> "Tool":
        async def exa_get_content(url: str) -> DocumentResponse:
            """Fetch and extract readable text from a URL via Exa.

            Returns the full document text, word count, and publication
            date when available.
            """
            return await self._run_skill(
                "exa_get_content",
                DocumentResponse,
                url=url,
            )

        return Tool(function=exa_get_content, takes_ctx=False)

    # ------------------------------------------------------------------
    # Report drafting tools
    # ------------------------------------------------------------------

    def _write_report_draft(self) -> "Tool":
        async def write_report_draft(
            relative_path: str,
            content: str,
        ) -> ReportWriteResponse:
            """Write a draft to ``/workspace/<relative_path>``.

            On success the file auto-publishes as a new row in the
            ``run_resources`` log so the manager can observe it via the
            graph toolkit.  Paths that escape ``/workspace/`` are rejected.
            """
            resp = await self._run_skill(
                "write_report_draft",
                ReportWriteResponse,
                relative_path=relative_path,
                content=content,
            )
            if resp.kind == "success":
                await self._publisher_sync()
            return resp

        return Tool(function=write_report_draft, takes_ctx=False)

    def _edit_report_draft(self) -> "Tool":
        async def edit_report_draft(
            relative_path: str,
            patch: str,
        ) -> ReportWriteResponse:
            """Apply a patch (replacement content) to a draft at
            ``/workspace/<relative_path>``.

            On success the updated file auto-publishes as a new row in
            the ``run_resources`` log.  Paths that escape ``/workspace/``
            are rejected.
            """
            resp = await self._run_skill(
                "edit_report_draft",
                ReportWriteResponse,
                relative_path=relative_path,
                patch=patch,
            )
            if resp.kind == "success":
                await self._publisher_sync()
            return resp

        return Tool(function=edit_report_draft, takes_ctx=False)

    def _read_report_draft(self) -> "Tool":
        async def read_report_draft(
            relative_path: str,
        ) -> ReportReadResponse:
            """Read a draft from ``/workspace/<relative_path>``.

            Read-only -- does not trigger a publish.
            """
            return await self._run_skill(
                "read_report_draft",
                ReportReadResponse,
                relative_path=relative_path,
            )

        return Tool(function=read_report_draft, takes_ctx=False)
