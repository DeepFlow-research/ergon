"""ResearchRubrics toolkit - Exa API tools for web research and report drafting."""

from uuid import UUID

from agents import function_tool, Tool

from h_arcane.core._internal.infrastructure.sandbox import BaseSandboxManager
from h_arcane.core._internal.agents.base import BaseToolkit, BaseStakeholder
from h_arcane.core._internal.communication import communication_service, CreateMessageRequest

# Import response types from skills
from h_arcane.benchmarks.researchrubrics.skills.responses import (
    ExaSearchResponse,
    ExaQAResponse,
    ExaGetContentResponse,
    WriteReportDraftResponse,
    EditReportDraftResponse,
    ReadReportDraftResponse,
)


class ResearchRubricsToolkit(BaseToolkit):
    """ResearchRubrics benchmark toolkit with Exa web research and report drafting tools.

    All tools execute inside the E2B sandbox via sandbox_manager.run_skill().
    The EXA_API_KEY environment variable is passed to the sandbox at creation.
    """

    def __init__(
        self,
        run_id: UUID,
        experiment_id: UUID,
        stakeholder: BaseStakeholder,
        sandbox_manager: BaseSandboxManager,
        max_questions: int = 10,
    ):
        """
        Initialize ResearchRubrics toolkit.

        Args:
            run_id: The run ID for logging messages and actions
            experiment_id: The experiment ID for traceability
            stakeholder: Stakeholder for answering questions
            sandbox_manager: Sandbox manager for skill execution
            max_questions: Maximum number of questions allowed
        """
        self.run_id = run_id
        self.experiment_id = experiment_id
        self.stakeholder = stakeholder
        self.sandbox_manager = sandbox_manager
        self.max_questions = max_questions
        self._questions_asked = 0

    @property
    def questions_asked(self) -> int:
        """Get number of questions asked so far."""
        return self._questions_asked

    def get_tools(self) -> list[Tool]:
        """Return all ResearchRubrics tools."""
        return [
            # Web research tools
            self._exa_search(),
            self._exa_qa(),
            self._exa_get_content(),
            # Report drafting tools
            self._write_report_draft(),
            self._edit_report_draft(),
            self._read_report_draft(),
            # Stakeholder interaction
            self._ask_stakeholder(),
        ]

    async def ask_stakeholder(self, question: str) -> str:
        """Ask the stakeholder a question directly.

        Args:
            question: The question to ask

        Returns:
            The stakeholder's response
        """
        if self._questions_asked >= self.max_questions:
            return f"[Maximum questions ({self.max_questions}) reached.]"

        worker_id = f"{self.run_id}:worker"
        stakeholder_id = f"{self.run_id}:stakeholder"
        thread_topic = "task_clarification"

        # Save worker question to thread
        communication_service.save_message(
            CreateMessageRequest(
                run_id=self.run_id,
                experiment_id=self.experiment_id,
                from_agent_id=worker_id,
                to_agent_id=stakeholder_id,
                thread_topic=thread_topic,
                content=question,
            )
        )

        # Get conversation history for stakeholder context
        threads = communication_service.get_all_threads_between_agents(worker_id, stakeholder_id)
        history = None
        if threads.threads:
            thread_data = communication_service.get_thread_messages(threads.threads[0].thread_id)
            if thread_data:
                # Exclude the question we just added (it's the last message)
                history = thread_data.messages[:-1] if thread_data.messages else None

        # Get answer with history context
        answer = await self.stakeholder.answer(question, history=history)

        # Save stakeholder answer to thread
        communication_service.save_message(
            CreateMessageRequest(
                run_id=self.run_id,
                experiment_id=self.experiment_id,
                from_agent_id=stakeholder_id,
                to_agent_id=worker_id,
                thread_topic=thread_topic,
                content=answer,
            )
        )

        self._questions_asked += 1
        return answer

    # ─────────────────────────────────────────────────────────────────
    # Web Research Tools - execute in sandbox via run_skill()
    # ─────────────────────────────────────────────────────────────────

    def _exa_search(self) -> Tool:
        @function_tool
        async def exa_search_tool(
            query: str,
            num_results: int = 5,
            category: str | None = None,
        ) -> ExaSearchResponse:
            """
            Search the web using Exa to get ranked search results with content.

            Args:
                query: Search query string
                num_results: Number of results to return (default: 5)
                category: Optional category filter ("news", "academic", "company")

            Returns:
                Response with search results including titles, URLs, summaries, and content.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id,
                "exa_search",
                ExaSearchResponse,
                query=query,
                num_results=num_results,
                category=category,
            )
            return result

        return exa_search_tool

    def _exa_qa(self) -> Tool:
        @function_tool
        async def exa_qa_tool(
            question: str,
            num_results: int = 3,
        ) -> ExaQAResponse:
            """
            Get direct answers to questions from web sources.

            Uses neural search optimized for Q&A to find and extract answers.

            Args:
                question: Question to answer
                num_results: Number of sources to use (default: 3)

            Returns:
                Response with answer and source citations.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id,
                "exa_qa",
                ExaQAResponse,
                question=question,
                num_results=num_results,
            )
            return result

        return exa_qa_tool

    def _exa_get_content(self) -> Tool:
        @function_tool
        async def exa_get_content_tool(url: str) -> ExaGetContentResponse:
            """
            Extract full content from a URL.

            Args:
                url: URL to extract content from

            Returns:
                Response with extracted content, title, and metadata.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id,
                "exa_get_content",
                ExaGetContentResponse,
                url=url,
            )
            return result

        return exa_get_content_tool

    # ─────────────────────────────────────────────────────────────────
    # Report Drafting Tools - execute in sandbox via run_skill()
    # ─────────────────────────────────────────────────────────────────

    def _write_report_draft(self) -> Tool:
        @function_tool
        async def write_report_draft_tool(
            content: str,
            file_path: str = "/workspace/final_output/report.md",
        ) -> WriteReportDraftResponse:
            """
            Write content to a markdown report file.

            Use this to create or overwrite the research report. The file will be
            downloaded after execution and evaluated against the rubric criteria.

            Args:
                content: The markdown content to write (full report)
                file_path: Path to write the file
                  - Use `/workspace/scratchpad/` for drafts (not evaluated)
                  - Use `/workspace/final_output/` for final report (default, evaluated)
                  - Default: `/workspace/final_output/report.md`

            Returns:
                Response with file path and bytes written.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id,
                "write_report_draft",
                WriteReportDraftResponse,
                content=content,
                file_path=file_path,
            )
            return result

        return write_report_draft_tool

    def _edit_report_draft(self) -> Tool:
        @function_tool
        async def edit_report_draft_tool(
            old_string: str,
            new_string: str,
            file_path: str = "/workspace/final_output/report.md",
        ) -> EditReportDraftResponse:
            """
            Edit the report using search and replace.

            Use this to make targeted edits to specific sections of the report.
            All occurrences of old_string will be replaced with new_string.

            Args:
                old_string: The text to find and replace
                new_string: The text to replace with
                file_path: Path to the file to edit (default: /workspace/final_output/report.md)

            Returns:
                Response with file path and number of replacements made.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id,
                "edit_report_draft",
                EditReportDraftResponse,
                old_string=old_string,
                new_string=new_string,
                file_path=file_path,
            )
            return result

        return edit_report_draft_tool

    def _read_report_draft(self) -> Tool:
        @function_tool
        async def read_report_draft_tool(
            file_path: str = "/workspace/final_output/report.md",
        ) -> ReadReportDraftResponse:
            """
            Read content from the report file.

            Use this to review the current state of the report before making edits.

            Args:
                file_path: Path to the file to read (default: /workspace/final_output/report.md)

            Returns:
                Response with file content.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id,
                "read_report_draft",
                ReadReportDraftResponse,
                file_path=file_path,
            )
            return result

        return read_report_draft_tool

    # ─────────────────────────────────────────────────────────────────
    # Stakeholder Interaction
    # ─────────────────────────────────────────────────────────────────

    def _ask_stakeholder(self) -> Tool:
        @function_tool
        async def ask_stakeholder_tool(question: str) -> str:
            """
            Ask the stakeholder a clarifying question about the research task.

            Use this when:
            - The task description is ambiguous or incomplete
            - You need to understand specific preferences
            - You want to clarify scope, depth, or format requirements

            Args:
                question: Your question for the stakeholder

            Returns:
                The stakeholder's response
            """
            return await self.ask_stakeholder(question)

        return ask_stakeholder_tool
