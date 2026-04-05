"""MiniF2F toolkit - explicit tool wrappers for Lean proof development."""

import re
from uuid import UUID

from e2b.sandbox.commands.command_handle import CommandExitException  # type: ignore[import-untyped]
from pydantic_ai.tools import Tool

from h_arcane.core._internal.infrastructure.sandbox import BaseSandboxManager
from h_arcane.core._internal.agents.base import BaseToolkit, BaseStakeholder
from h_arcane.core._internal.communication import communication_service, CreateMessageRequest
from h_arcane.core.worker import QAExchange


# Import response types from the skills package
from h_arcane.benchmarks.minif2f.skills.responses import (
    WriteLeanResponse,
    LeanCheckResponse,
    LeanVerificationResponse,
    SearchLemmasResponse,
)

# Lean command prefix - runs from Mathlib project directory for access to imports
# NOTE: Mathlib is installed in /tools (not /workspace) to avoid downloading all library
# files as outputs when the run completes.
LEAN_CMD_PREFIX = "export PATH=$HOME/.elan/bin:$PATH && cd /tools/mathlib_project/src &&"


def _parse_lean_output(output: str) -> tuple[list[str], list[str]]:
    """Parse Lean compiler output to extract errors and goals.

    Args:
        output: Combined stdout and stderr from Lean compiler

    Returns:
        Tuple of (errors, goals_remaining)
    """
    errors: list[str] = []
    goals: list[str] = []

    lines = output.split("\n")
    error_pattern = re.compile(r"^.*:\d+:\d+:\s*(error|warning):\s*(.+)$")
    goal_pattern = re.compile(r"⊢\s*(.+)$")

    current_error: list[str] = []
    in_error = False

    for line in lines:
        line = line.strip()

        error_match = error_pattern.match(line)
        if error_match:
            if current_error:
                errors.append("\n".join(current_error))
            current_error = [line]
            in_error = True
            continue

        goal_match = goal_pattern.search(line)
        if goal_match:
            goal_text = goal_match.group(1).strip()
            if goal_text:
                goals.append(goal_text)

        if in_error and line:
            current_error.append(line)
        elif in_error and not line:
            if current_error:
                errors.append("\n".join(current_error))
            current_error = []
            in_error = False

    if current_error:
        errors.append("\n".join(current_error))

    return errors, goals


class MiniF2FToolkit(BaseToolkit):
    """MiniF2F benchmark toolkit with Lean tools."""

    def __init__(
        self,
        task_id: UUID,
        run_id: UUID,
        experiment_id: UUID,
        stakeholder: BaseStakeholder,
        sandbox_manager: BaseSandboxManager,
        max_questions: int = 10,
    ):
        """
        Initialize MiniF2F toolkit.

        Args:
            task_id: The task ID for sandbox keying (sandboxes are per-task)
            run_id: The run ID for communication service
            experiment_id: The experiment ID for communication service
            stakeholder: Stakeholder for providing proof hints
            sandbox_manager: BaseSandboxManager for skill execution
            max_questions: Maximum number of questions allowed
        """
        self.task_id = task_id
        self.run_id = run_id
        self.experiment_id = experiment_id
        self.stakeholder = stakeholder
        self.sandbox_manager = sandbox_manager
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
        """Return all MiniF2F tools."""
        return [
            self._write_lean_file(),
            self._check_lean_file(),
            self._verify_lean_proof(),
            self._search_lemmas(),
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

        # Accumulate Q&A history for WorkerResult
        self._qa_history.append(QAExchange(question=question, answer=answer))

        self._questions_asked += 1
        return answer

    # ─────────────────────────────────────────────────────────────────
    # Lean-specific tool wrappers
    # ─────────────────────────────────────────────────────────────────

    def _write_lean_file(self) -> Tool:
        async def write_lean_file(file_path: str, content: str) -> WriteLeanResponse:
            """
            Write or update a Lean proof file.

            Use `sorry` as a placeholder for incomplete proofs - check_lean_file
            will show you the proof goals.

            Args:
                file_path: Full path to the file
                  - Use `/workspace/scratchpad/draft.lean` for drafts/experimentation
                  - Use `/workspace/final_output/final_solution.lean` for your final submission
                content: Complete Lean file content

            IMPORTANT: Your final proof MUST be written to `/workspace/final_output/final_solution.lean`.
            This is the ONLY file that will be evaluated.

            Returns:
                Response model with bytes written, or error message.
            """
            result = await self.sandbox_manager.run_skill(
                self.run_id,
                "write_lean_file",
                WriteLeanResponse,
                file_path=file_path,
                content=content,
            )
            return result

        return Tool(function=write_lean_file, takes_ctx=False)

    def _check_lean_file(self) -> Tool:
        async def check_lean_file(file_path: str) -> LeanCheckResponse:
            """
            Check a Lean file for errors and get proof goals.

            Use this after write_lean_file to see:
            - Syntax/type errors
            - Unsolved goals (what you need to prove)
            - Warnings

            Args:
                file_path: Full path to the Lean file to check
                  - `/workspace/scratchpad/draft.lean` for drafts
                  - `/workspace/final_output/final_solution.lean` for final

            Returns:
                Response model with errors, goals, and warnings.
            """
            # Get sandbox and run Lean directly via shell command
            # This uses the same shell environment where Lean was installed
            sandbox = self.sandbox_manager.get_sandbox(self.run_id)
            if not sandbox:
                return LeanCheckResponse(
                    success=False,
                    error="Sandbox not available",
                )

            try:
                # Run Lean compiler via sandbox shell (same env where it was installed)
                # Use absolute path - Lean can compile files from any location
                cmd = f"{LEAN_CMD_PREFIX} lean {file_path} 2>&1"
                try:
                    result = await sandbox.commands.run(cmd, timeout=60)
                    output = (result.stdout or "") + (result.stderr or "")
                    exit_code = result.exit_code
                except CommandExitException as cmd_err:
                    # Non-zero exit is expected for Lean errors - extract output
                    output = (cmd_err.stdout or "") + (cmd_err.stderr or "")
                    exit_code = cmd_err.exit_code

                # Parse output for errors and goals
                errors, goals = _parse_lean_output(output)

                # File compiled if exit code is 0 OR if it has sorry (partial proof)
                compiled = exit_code == 0 or "sorry" in output

                return LeanCheckResponse(
                    success=True,
                    compiled=compiled,
                    errors=errors if errors else None,
                    goals_remaining=goals if goals else None,
                )

            except Exception as e:
                return LeanCheckResponse(
                    success=False,
                    error=f"Error checking Lean file: {e}",
                )

        return Tool(function=check_lean_file, takes_ctx=False)

    def _verify_lean_proof(self) -> Tool:
        async def verify_lean_proof(file_path: str) -> LeanVerificationResponse:
            """
            Verify a complete Lean proof (no `sorry` allowed).

            Call this when you believe your proof is complete.
            The proof must compile without errors and contain no `sorry`.

            Args:
                file_path: Full path to the Lean file to verify
                  - Use `/workspace/final_output/final_solution.lean` for your final submission

            IMPORTANT: Before submitting, verify `/workspace/final_output/final_solution.lean` -
            this is the only file that will be evaluated for scoring.

            Returns:
                Response model with verification result and details.
            """
            # Get sandbox and run Lean directly via shell command
            sandbox = self.sandbox_manager.get_sandbox(self.run_id)
            if not sandbox:
                return LeanVerificationResponse(
                    success=False,
                    verified=False,
                    error="Sandbox not available",
                )

            try:
                # First read the file to check for sorry
                file_content = await sandbox.files.read(file_path)
                if isinstance(file_content, bytes):
                    file_content = file_content.decode("utf-8")

                if "sorry" in file_content:
                    return LeanVerificationResponse(
                        success=True,
                        verified=False,
                        message="Proof contains 'sorry' - incomplete proof not allowed for verification",
                    )

                # Run Lean compiler via sandbox shell
                # Note: Lean 3 doesn't have a --check flag, just compile the file
                cmd = f"{LEAN_CMD_PREFIX} lean {file_path} 2>&1"
                try:
                    result = await sandbox.commands.run(cmd, timeout=60)
                    output = (result.stdout or "") + (result.stderr or "")
                    exit_code = result.exit_code
                except CommandExitException as cmd_err:
                    # Non-zero exit means verification failed - extract output
                    output = (cmd_err.stdout or "") + (cmd_err.stderr or "")
                    exit_code = cmd_err.exit_code

                verified = exit_code == 0

                if verified:
                    return LeanVerificationResponse(
                        success=True,
                        verified=True,
                        message="Proof verified successfully!",
                        output=output,
                    )
                else:
                    return LeanVerificationResponse(
                        success=True,
                        verified=False,
                        message="Proof verification failed",
                        error=output,
                    )

            except Exception as e:
                return LeanVerificationResponse(
                    success=False,
                    verified=False,
                    error=f"Error verifying Lean proof: {e}",
                )

        return Tool(function=verify_lean_proof, takes_ctx=False)

    def _search_lemmas(self) -> Tool:
        async def search_lemmas(query: str) -> SearchLemmasResponse:
            """
            Search for lemmas, definitions, or check types in Mathlib.

            Use this to find available lemmas or check if a name exists.

            Examples:
                - search_lemmas("#check mul_comm") - Check type of mul_comm
                - search_lemmas("#check @finset.sum") - Check finset.sum signature
                - search_lemmas("#print mul_comm") - Print full definition
                - search_lemmas("#check (∑ x in s, f x)") - Check type of expression

            Args:
                query: A Lean query like "#check lemma_name" or "#print lemma_name"

            Returns:
                Structured output showing the Lean result or a search failure.
            """
            sandbox = self.sandbox_manager.get_sandbox(self.run_id)
            if not sandbox:
                return SearchLemmasResponse(
                    success=False,
                    query=query,
                    error="Sandbox not available",
                )

            try:
                # Create a temporary Lean file with the query
                # Include common imports so we can search Mathlib
                lean_content = f"""import tactic
import data.real.basic
import data.complex.basic
import data.nat.basic
import data.int.basic
import data.finset.basic
import algebra.big_operators.basic

{query}
"""
                # Write to a temp file
                temp_file = "_search_query.lean"
                await sandbox.files.write(
                    f"/tools/mathlib_project/src/{temp_file}",
                    lean_content.encode("utf-8"),
                )

                # Run Lean on it
                cmd = f"{LEAN_CMD_PREFIX} lean {temp_file} 2>&1"
                try:
                    result = await sandbox.commands.run(cmd, timeout=30)
                    output = (result.stdout or "") + (result.stderr or "")
                except CommandExitException as cmd_err:
                    output = (cmd_err.stdout or "") + (cmd_err.stderr or "")

                # Clean up the output - remove file path prefixes
                lines = output.strip().split("\n")
                cleaned_lines = []
                for line in lines:
                    # Remove the file:line:col prefix for cleaner output
                    if "_search_query.lean:" in line:
                        # Extract just the message part
                        parts = line.split(":", 3)
                        if len(parts) >= 4:
                            cleaned_lines.append(parts[3].strip())
                        else:
                            cleaned_lines.append(line)
                    else:
                        cleaned_lines.append(line)

                return SearchLemmasResponse(
                    success=True,
                    query=query,
                    output="\n".join(cleaned_lines).strip() or "No output from query",
                )

            except Exception as e:
                return SearchLemmasResponse(
                    success=False,
                    query=query,
                    error=f"Error searching: {e}",
                )

        return Tool(function=search_lemmas, takes_ctx=False)

    def _ask_stakeholder(self) -> Tool:
        async def ask_stakeholder(question: str) -> str:
            """
            Ask for a hint about the proof strategy.

            Args:
                question: Your question about the proof

            Returns:
                A hint or guidance from the stakeholder.
            """
            return await self.ask_stakeholder(question)

        return Tool(function=ask_stakeholder, takes_ctx=False)
