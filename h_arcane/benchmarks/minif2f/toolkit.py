"""MiniF2F toolkit with ask_stakeholder and Lean tools."""

from uuid import UUID
from agents import Tool

from h_arcane.agents.sandbox import SandboxManager
from h_arcane.agents.sandbox_executor import set_sandbox_manager
from h_arcane.benchmarks.base import BaseToolkit
from h_arcane.benchmarks.minif2f.stakeholder import MiniF2FStakeholder
from h_arcane.agents.tools import (
    write_lean_file,
    check_lean_file,
    verify_lean_proof,
)
from h_arcane.db.models import Message, MessageRole
from h_arcane.db.queries import queries


class MiniF2FToolkit(BaseToolkit):
    """
    MiniF2F-specific toolkit.

    Tools available to the worker during execution:
    - ask_stakeholder: Ask for proof hints (executes outside sandbox)
    - Lean tools: write_lean_file, check_lean_file, verify_lean_proof (execute in E2B sandbox)
    """

    def __init__(
        self,
        run_id: UUID,
        stakeholder: MiniF2FStakeholder,
        sandbox_manager: SandboxManager,
        max_questions: int = 10,
    ):
        """
        Initialize MiniF2F toolkit.

        Args:
            run_id: The run ID for logging messages and actions
            stakeholder: MiniF2FStakeholder for providing proof hints
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
        Ask the stakeholder for a proof hint.

        Args:
            question: The question to ask about proof strategy

        Returns:
            Hint from stakeholder, or message if max questions reached

        Example:
            ```python
            hint = await toolkit.ask_stakeholder("What strategy should I use?")
            # Returns: "Consider using induction on n..."
            ```
        """
        if self._questions_asked >= self.max_questions:
            return f"[Maximum questions ({self.max_questions}) reached.]"

        # Log worker question
        queries.messages.create(
            Message(
                run_id=self.run_id,
                sender=MessageRole.WORKER,
                content=question,
                sequence_num=self._message_num,
            )
        )
        self._message_num += 1

        # Get answer
        answer = await self.stakeholder.answer(question)

        # Log stakeholder answer
        queries.messages.create(
            Message(
                run_id=self.run_id,
                sender=MessageRole.STAKEHOLDER,
                content=answer,
                sequence_num=self._message_num,
            )
        )
        self._message_num += 1

        self._questions_asked += 1
        return answer

    @property
    def questions_asked(self) -> int:
        """Get number of questions asked so far."""
        return self._questions_asked

    def get_tools(self) -> list[Tool]:
        """
        Get MiniF2F tools that execute in sandbox.

        Returns:
            List of tool functions decorated with @function_tool

        Example:
            ```python
            tools = toolkit.get_tools()
            # Returns: [write_lean_file, check_lean_file, verify_lean_proof]
            ```
        """
        # Set sandbox manager for execute_in_sandbox()
        set_sandbox_manager(self.sandbox_manager, self.run_id)

        # Return Lean tool functions
        return [
            write_lean_file,
            check_lean_file,
            verify_lean_proof,
        ]
