"""MiniF2F toolkit - explicit tool wrappers for Lean proof development."""

from uuid import UUID

from agents import function_tool, Tool

from h_arcane.core.infrastructure.sandbox import SandboxManager
from h_arcane.core.agents.base import BaseToolkit, BaseStakeholder
from h_arcane.core.db.models import Message, MessageRole
from h_arcane.core.db.queries import queries

# Import response types from the skills package (same types used in VM!)
from h_arcane.benchmarks.minif2f.skills.responses import (
    WriteLeanResponse,
    LeanCheckResponse,
    LeanVerificationResponse,
)


class MiniF2FToolkit(BaseToolkit):
    """MiniF2F benchmark toolkit with Lean tools."""

    def __init__(
        self,
        run_id: UUID,
        stakeholder: BaseStakeholder,
        sandbox_manager: SandboxManager,
        max_questions: int = 10,
    ):
        """
        Initialize MiniF2F toolkit.

        Args:
            run_id: The run ID for logging messages and actions
            stakeholder: Stakeholder for providing proof hints
            sandbox_manager: SandboxManager for skill execution
            max_questions: Maximum number of questions allowed
        """
        self.run_id = run_id
        self.stakeholder = stakeholder
        self.sandbox_manager = sandbox_manager
        self.max_questions = max_questions
        self._questions_asked = 0
        self._message_num = 0

    @property
    def questions_asked(self) -> int:
        """Get number of questions asked so far."""
        return self._questions_asked

    def get_tools(self) -> list[Tool]:
        """Return all MiniF2F tools."""
        return [
            self._write_lean_file(),
            self._check_lean_file(),
            self._verify_lean_proof(),
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

    # ─────────────────────────────────────────────────────────────────
    # Lean-specific tool wrappers
    # ─────────────────────────────────────────────────────────────────

    def _write_lean_file(self) -> Tool:
        @function_tool
        async def write_lean_file(filename: str, content: str) -> WriteLeanResponse:
            """
            Write or update a Lean proof file.

            Use `sorry` as a placeholder for incomplete proofs - check_lean_file
            will show you the proof goals.

            Args:
                filename: Name of the file (e.g., "proof.lean")
                content: Complete Lean file content

            Returns:
                Response model with bytes written, or error message.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id,
                "write_lean_file",
                WriteLeanResponse,
                filename=filename,
                content=content,
            )
            return result

        return write_lean_file

    def _check_lean_file(self) -> Tool:
        @function_tool
        async def check_lean_file(filename: str) -> LeanCheckResponse:
            """
            Check a Lean file for errors and get proof goals.

            Use this after write_lean_file to see:
            - Syntax/type errors
            - Unsolved goals (what you need to prove)
            - Warnings

            Args:
                filename: Name of the Lean file to check

            Returns:
                Response model with errors, goals, and warnings.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id,
                "check_lean_file",
                LeanCheckResponse,
                filename=filename,
            )
            return result

        return check_lean_file

    def _verify_lean_proof(self) -> Tool:
        @function_tool
        async def verify_lean_proof(filename: str) -> LeanVerificationResponse:
            """
            Verify a complete Lean proof (no `sorry` allowed).

            Call this when you believe your proof is complete.
            The proof must compile without errors and contain no `sorry`.

            Args:
                filename: Name of the Lean file to verify

            Returns:
                Response model with verification result and details.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id,
                "verify_lean_proof",
                LeanVerificationResponse,
                filename=filename,
            )
            return result

        return verify_lean_proof

    def _ask_stakeholder(self) -> Tool:
        @function_tool
        async def ask_stakeholder(question: str) -> str:
            """
            Ask for a hint about the proof strategy.

            Args:
                question: Your question about the proof

            Returns:
                A hint or guidance from the stakeholder.
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

        return ask_stakeholder
