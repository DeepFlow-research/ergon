"""Worker toolkit with ask_stakeholder and GDPEval tools."""

from uuid import UUID
from agents import Tool

from h_arcane.agents.sandbox import SandboxManager
from h_arcane.agents.sandbox_executor import set_sandbox_manager
from h_arcane.agents.stakeholder import RubricStakeholder
from h_arcane.agents.tools import (
    read_pdf,
    create_docx,
    read_excel,
    create_excel,
    read_csv,
    create_csv,
    execute_python_code,
    ocr_image,
)
from h_arcane.db.models import MessageRole
from h_arcane.db.queries import queries


class WorkerToolkit:
    """
    Tools available to the worker during execution.

    - ask_stakeholder: Clarification tool (executes outside sandbox)
    - GDPEval tools: Documents, spreadsheets, OCR, code execution (execute in E2B sandbox)

    See SANDBOX_ARCHITECTURE.md for sandbox execution details.
    """

    def __init__(
        self,
        run_id: UUID,
        stakeholder: RubricStakeholder,
        sandbox_manager: SandboxManager,
        max_questions: int = 10,
    ):
        """
        Initialize worker toolkit.

        Args:
            run_id: The run ID for logging messages and actions
            stakeholder: RubricStakeholder for answering questions
            sandbox_manager: SandboxManager for tool execution
            max_questions: Maximum number of questions allowed
        """
        self.run_id = run_id
        self.stakeholder = stakeholder
        self.sandbox_manager = sandbox_manager
        self.max_questions = max_questions
        self._questions_asked = 0
        self._action_num = 0
        self._message_num = 0

    async def ask_stakeholder(self, question: str) -> str:
        """
        Ask the stakeholder a clarification question.

        Args:
            question: The question to ask

        Returns:
            Answer from stakeholder, or message if max questions reached

        Example:
            ```python
            answer = await toolkit.ask_stakeholder("What format should the output be?")
            # Returns: "The output should be a PDF document..."
            ```
        """
        if self._questions_asked >= self.max_questions:
            return f"[Maximum questions ({self.max_questions}) reached.]"

        # Log worker question
        queries.messages.create(
            run_id=self.run_id,
            sender=MessageRole.WORKER,
            content=question,
            sequence_num=self._message_num,
        )
        self._message_num += 1

        # Get answer
        answer = await self.stakeholder.answer(question)

        # Log stakeholder answer
        queries.messages.create(
            run_id=self.run_id,
            sender=MessageRole.STAKEHOLDER,
            content=answer,
            sequence_num=self._message_num,
        )
        self._message_num += 1

        # Note: Action logging is now handled by ActionLoggingHooks in worker.py
        # No need to manually log ask_stakeholder actions here

        self._questions_asked += 1
        return answer

    @property
    def questions_asked(self) -> int:
        """Get number of questions asked so far."""
        return self._questions_asked

    def get_gdpeval_tools(self) -> list[Tool]:
        """
        Get GDPEval tools that execute in sandbox.

        Returns:
            List of tool functions decorated with @function_tool

        Example:
            ```python
            tools = toolkit.get_gdpeval_tools()
            # Returns: [read_pdf, create_docx, read_excel, create_excel, ...]
            ```
        """
        # Set sandbox manager for execute_in_sandbox()
        set_sandbox_manager(self.sandbox_manager, self.run_id)

        # Return tool functions (they're @function_tool decorated and call execute_in_sandbox internally)
        return [
            read_pdf,
            create_docx,
            read_excel,
            create_excel,
            read_csv,
            create_csv,
            execute_python_code,
            ocr_image,
        ]
