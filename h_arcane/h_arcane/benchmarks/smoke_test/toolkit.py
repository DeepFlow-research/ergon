"""Smoke test toolkit - stub tools that return mock data instantly."""

from uuid import UUID

from pydantic_ai.tools import Tool

from h_arcane.core._internal.infrastructure.sandbox import BaseSandboxManager
from h_arcane.core._internal.agents.base import BaseToolkit, BaseStakeholder
from h_arcane.core._internal.communication import communication_service, CreateMessageRequest
from h_arcane.core.worker import QAExchange

from h_arcane.benchmarks.smoke_test.stub_responses import (
    StubReadFileResponse,
    StubWriteFileResponse,
    StubAnalyzeResponse,
)


class SmokeTestToolkit(BaseToolkit):
    """Smoke test toolkit with stub tools that return mock data instantly.

    This toolkit is designed for pipeline validation without requiring
    a real E2B sandbox. All tools return predetermined mock responses.
    """

    def __init__(
        self,
        task_id: UUID,
        run_id: UUID,
        experiment_id: UUID,
        stakeholder: BaseStakeholder,
        sandbox_manager: BaseSandboxManager,
        max_questions: int = 3,
    ):
        """
        Initialize SmokeTest toolkit.

        Args:
            task_id: The task ID (for consistency with other toolkits)
            run_id: The run ID for communication service
            experiment_id: The experiment ID for communication service
            stakeholder: Stakeholder for answering questions
            sandbox_manager: Sandbox manager (not used - tools are stubs)
            max_questions: Maximum number of questions allowed
        """
        self.task_id = task_id
        self.run_id = run_id
        self.experiment_id = experiment_id
        self.stakeholder = stakeholder
        self.sandbox_manager = sandbox_manager  # Kept for interface consistency
        self.max_questions = max_questions
        self._questions_asked = 0
        self._qa_history: list[QAExchange] = []

    @property
    def questions_asked(self) -> int:
        """Get number of questions asked so far."""
        return self._questions_asked

    def get_qa_history(self) -> list[QAExchange]:
        """Return Q&A history for inclusion in WorkerResult."""
        return self._qa_history

    def get_tools(self) -> list[Tool]:
        """Return all smoke test tools."""
        return [
            self._read_file(),
            self._write_file(),
            self._analyze_data(),
            self._ask_stakeholder(),
        ]

    async def ask_stakeholder(self, question: str) -> str:
        """Ask the stakeholder a question directly."""
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

        # Accumulate Q&A history for WorkerResult
        self._qa_history.append(QAExchange(question=question, answer=answer))

        self._questions_asked += 1
        return answer

    # ─────────────────────────────────────────────────────────────────
    # Stub tool implementations - return mock data instantly
    # ─────────────────────────────────────────────────────────────────

    def _read_file(self) -> Tool:
        async def read_file(file_path: str) -> StubReadFileResponse:
            """
            Read contents of a file (stub - returns mock data).

            Args:
                file_path: Path to the file to read

            Returns:
                Response with mock file content.
            """
            # Generate mock content based on file type
            if file_path.endswith(".csv"):
                content = "id,name,value\n1,test_item,100\n2,sample,200\n3,data,300"
            elif file_path.endswith(".json"):
                content = '{"key": "value", "items": [1, 2, 3], "nested": {"a": true}}'
            else:
                content = (
                    f"Mock content for file: {file_path}\nThis is stub data for smoke testing."
                )

            return StubReadFileResponse(
                success=True,
                content=content,
                size_bytes=len(content),
            )

        return Tool(function=read_file, takes_ctx=False)

    def _write_file(self) -> Tool:
        async def write_file(file_path: str, content: str) -> StubWriteFileResponse:
            """
            Write content to a file (stub - returns mock success).

            Args:
                file_path: Path where to write the file
                content: Content to write

            Returns:
                Response with mock success status.
            """
            return StubWriteFileResponse(
                success=True,
                path=file_path,
                size_bytes=len(content),
            )

        return Tool(function=write_file, takes_ctx=False)

    def _analyze_data(self) -> Tool:
        async def analyze_data(data_description: str) -> StubAnalyzeResponse:
            """
            Analyze data based on description (stub - returns mock findings).

            Args:
                data_description: Description of what to analyze

            Returns:
                Response with mock analysis findings.
            """
            return StubAnalyzeResponse(
                success=True,
                summary=f"Analysis of: {data_description}",
                findings=[
                    "Finding 1: Data shows expected patterns",
                    "Finding 2: No anomalies detected in smoke test",
                    "Finding 3: Pipeline validation successful",
                ],
            )

        return Tool(function=analyze_data, takes_ctx=False)

    def _ask_stakeholder(self) -> Tool:
        async def ask_stakeholder(question: str) -> str:
            """
            Ask the stakeholder a clarifying question.

            Args:
                question: Your question for the stakeholder

            Returns:
                The stakeholder's response.
            """
            return await self.ask_stakeholder(question)

        return Tool(function=ask_stakeholder, takes_ctx=False)
