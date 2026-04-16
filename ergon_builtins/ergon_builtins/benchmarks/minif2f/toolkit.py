"""MiniF2F toolkit — Lean proof-assistant tool definitions.

Provides Pydantic response models and a ``MiniF2FToolkit`` that produces
``pydantic_ai.tools.Tool`` wrappers for:

- Writing / checking / verifying Lean proof files
- Searching Mathlib for lemmas
- Stakeholder interaction (proof hints)
"""

import re

from pydantic import BaseModel, Field

try:
    from pydantic_ai.tools import Tool
except ImportError:
    Tool = None  # type: ignore[assignment,misc]

from ergon_builtins.benchmarks.minif2f.constants import LEAN_CMD, LEAN_CMD_PREFIX

# ── Response models ───────────────────────────────────────────────────


class WriteLeanResponse(BaseModel):
    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    filename: str | None = Field(default=None, description="Path to the written file")
    bytes_written: int | None = Field(default=None, description="Number of bytes written")


class LeanCheckResponse(BaseModel):
    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    compiled: bool = Field(default=False, description="Whether the file compiled (sorry allowed)")
    errors: list[str] | None = Field(default=None, description="Compilation errors if any")
    goals_remaining: list[str] | None = Field(
        default=None, description="Goals from sorry placeholders"
    )
    warnings: list[str] | None = Field(default=None, description="Compiler warnings")


class LeanVerificationResponse(BaseModel):
    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    verified: bool = Field(
        default=False,
        description="Whether the proof compiled and verified (no sorry)",
    )
    message: str | None = Field(default=None, description="Verification result message")
    output: str | None = Field(default=None, description="Lean compiler output")


class SearchLemmasResponse(BaseModel):
    success: bool = Field(description="Whether the search completed successfully")
    error: str | None = Field(default=None, description="Error message if the search failed")
    query: str | None = Field(default=None, description="The Lean query that was executed")
    output: str | None = Field(default=None, description="Lean output for the query")


# ── Helpers ───────────────────────────────────────────────────────────


def parse_lean_output(output: str) -> tuple[list[str], list[str]]:
    """Parse Lean compiler output to extract errors and unsolved goals.

    Returns (errors, goals_remaining).
    """
    errors: list[str] = []
    goals: list[str] = []

    error_pattern = re.compile(r"^.*:\d+:\d+:\s*(error|warning):\s*(.+)$")
    goal_pattern = re.compile(r"⊢\s*(.+)$")

    current_error: list[str] = []
    in_error = False

    for raw_line in output.split("\n"):
        line = raw_line.strip()

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


# ── Toolkit ───────────────────────────────────────────────────────────


class MiniF2FToolkit:
    """Produces ``pydantic_ai.tools.Tool`` instances for Lean proof development.

    Parameters
    ----------
    sandbox:
        An E2B sandbox instance (or compatible) with ``commands.run()``
        and ``files`` interfaces.
    ask_stakeholder_fn:
        Async callable ``(question) -> answer`` for stakeholder hints.
    sandbox_run_skill:
        Async callable ``(run_id, skill_name, response_model, **kwargs)``
        for write_lean_file skill execution.
    run_id:
        Opaque run identifier forwarded to ``sandbox_run_skill``.
    """

    def __init__(
        self,
        *,
        sandbox,
        sandbox_run_skill,
        run_id,
        ask_stakeholder_fn=None,
    ) -> None:
        self._sandbox = sandbox
        self._ask = ask_stakeholder_fn
        self._run_skill = sandbox_run_skill
        self._run_id = run_id

    def get_tools(self) -> list[Tool]:
        tools = [
            self._write_lean_file(),
            self._check_lean_file(),
            self._verify_lean_proof(),
            self._search_lemmas(),
        ]
        if self._ask is not None:
            tools.append(self._ask_stakeholder())
        return tools

    # ── Lean tools ────────────────────────────────────────────────────

    def _write_lean_file(self) -> Tool:
        async def write_lean_file(file_path: str, content: str) -> WriteLeanResponse:
            """Write or update a Lean proof file.

            Use ``sorry`` as a placeholder for incomplete proofs.

            Args:
                file_path: Full path to the file.
                    /workspace/scratchpad/draft.lean for drafts.
                    /workspace/final_output/final_solution.lean for final submission.
                content: Complete Lean file content.
            """
            return await self._run_skill(
                self._run_id,
                "write_lean_file",
                WriteLeanResponse,
                file_path=file_path,
                content=content,
            )

        return Tool(function=write_lean_file, takes_ctx=False)

    def _check_lean_file(self) -> Tool:
        sandbox = self._sandbox

        async def check_lean_file(file_path: str) -> LeanCheckResponse:
            """Check a Lean file for errors and get proof goals.

            Args:
                file_path: Full path to the Lean file to check.
            """
            if sandbox is None:
                return LeanCheckResponse(success=False, error="Sandbox not available")

            try:
                cmd = f"{LEAN_CMD_PREFIX} {LEAN_CMD} {file_path} 2>&1"
                try:  # slopcop: ignore[no-nested-try]
                    result = await sandbox.commands.run(cmd, timeout=60)
                    output = (result.stdout or "") + (result.stderr or "")
                    exit_code = result.exit_code
                except Exception as cmd_err:  # slopcop: ignore[no-broad-except]
                    e = cmd_err
                    _out = getattr(e, "stdout", "")  # slopcop: ignore[no-hasattr-getattr]
                    _err = getattr(e, "stderr", "")  # slopcop: ignore[no-hasattr-getattr]
                    output = (_out or "") + (_err or "")
                    exit_code = getattr(e, "exit_code", 1)  # slopcop: ignore[no-hasattr-getattr]

                errors, goals = parse_lean_output(output)
                compiled = exit_code == 0 or "sorry" in output

                return LeanCheckResponse(
                    success=True,
                    compiled=compiled,
                    errors=errors or None,
                    goals_remaining=goals or None,
                )
            except Exception as exc:  # slopcop: ignore[no-broad-except]
                return LeanCheckResponse(success=False, error=f"Error checking Lean file: {exc}")

        return Tool(function=check_lean_file, takes_ctx=False)

    def _verify_lean_proof(self) -> Tool:
        sandbox = self._sandbox

        async def verify_lean_proof(file_path: str) -> LeanVerificationResponse:
            """Verify a complete Lean proof (no ``sorry`` allowed).

            Args:
                file_path: Full path to the Lean file to verify.
            """
            if sandbox is None:
                return LeanVerificationResponse(
                    success=False, verified=False, error="Sandbox not available"
                )

            try:
                file_content = await sandbox.files.read(file_path)
                if isinstance(file_content, bytes):
                    file_content = file_content.decode("utf-8")

                if "sorry" in file_content:
                    return LeanVerificationResponse(
                        success=True,
                        verified=False,
                        message=(
                            "Proof contains 'sorry' — incomplete proof not allowed for verification"
                        ),
                    )

                cmd = f"{LEAN_CMD_PREFIX} {LEAN_CMD} {file_path} 2>&1"
                try:  # slopcop: ignore[no-nested-try]
                    result = await sandbox.commands.run(cmd, timeout=60)
                    output = (result.stdout or "") + (result.stderr or "")
                    exit_code = result.exit_code
                except Exception as cmd_err:  # slopcop: ignore[no-broad-except]
                    e = cmd_err
                    _out = getattr(e, "stdout", "")  # slopcop: ignore[no-hasattr-getattr]
                    _err = getattr(e, "stderr", "")  # slopcop: ignore[no-hasattr-getattr]
                    output = (_out or "") + (_err or "")
                    exit_code = getattr(e, "exit_code", 1)  # slopcop: ignore[no-hasattr-getattr]

                verified = exit_code == 0

                if verified:
                    return LeanVerificationResponse(
                        success=True,
                        verified=True,
                        message="Proof verified successfully!",
                        output=output,
                    )
                return LeanVerificationResponse(
                    success=True,
                    verified=False,
                    message="Proof verification failed",
                    error=output,
                )
            except Exception as exc:  # slopcop: ignore[no-broad-except]
                return LeanVerificationResponse(
                    success=False,
                    verified=False,
                    error=f"Error verifying Lean proof: {exc}",
                )

        return Tool(function=verify_lean_proof, takes_ctx=False)

    def _search_lemmas(self) -> Tool:
        sandbox = self._sandbox

        async def search_lemmas(query: str) -> SearchLemmasResponse:
            """Search for lemmas, definitions, or check types in Mathlib.

            Examples:
                search_lemmas("#check mul_comm")
                search_lemmas("#check @finset.sum")
                search_lemmas("#print mul_comm")

            Args:
                query: A Lean query like ``#check lemma_name`` or ``#print lemma_name``.
            """
            if sandbox is None:
                return SearchLemmasResponse(
                    success=False, query=query, error="Sandbox not available"
                )

            try:
                lean_content = (
                    "import tactic\n"
                    "import data.real.basic\n"
                    "import data.complex.basic\n"
                    "import data.nat.basic\n"
                    "import data.int.basic\n"
                    "import data.finset.basic\n"
                    "import algebra.big_operators.basic\n\n"
                    f"{query}\n"
                )

                temp_file = "_search_query.lean"
                await sandbox.files.write(
                    f"/tools/mathlib_project/src/{temp_file}",
                    lean_content.encode("utf-8"),
                )

                cmd = f"{LEAN_CMD_PREFIX} {LEAN_CMD} src/{temp_file} 2>&1"
                try:  # slopcop: ignore[no-nested-try]
                    result = await sandbox.commands.run(cmd, timeout=30)
                    output = (result.stdout or "") + (result.stderr or "")
                except Exception as cmd_err:  # slopcop: ignore[no-broad-except]
                    _stdout = getattr(cmd_err, "stdout", "")  # slopcop: ignore[no-hasattr-getattr]
                    _stderr = getattr(cmd_err, "stderr", "")  # slopcop: ignore[no-hasattr-getattr]
                    output = (_stdout or "") + (_stderr or "")

                cleaned_lines: list[str] = []
                for line in output.strip().split("\n"):
                    if "_search_query.lean:" in line:
                        parts = line.split(":", 3)
                        cleaned_lines.append(parts[3].strip() if len(parts) >= 4 else line)
                    else:
                        cleaned_lines.append(line)

                return SearchLemmasResponse(
                    success=True,
                    query=query,
                    output="\n".join(cleaned_lines).strip() or "No output from query",
                )
            except Exception as exc:  # slopcop: ignore[no-broad-except]
                return SearchLemmasResponse(
                    success=False, query=query, error=f"Error searching: {exc}"
                )

        return Tool(function=search_lemmas, takes_ctx=False)

    # ── Stakeholder ───────────────────────────────────────────────────

    def _ask_stakeholder(self) -> Tool:
        async def ask_stakeholder(question: str) -> str:
            """Ask for a hint about the proof strategy.

            Args:
                question: Your question about the proof.
            """
            if self._ask is None:
                raise RuntimeError("ask_stakeholder called but no callback was provided")
            return await self._ask(question)

        return Tool(function=ask_stakeholder, takes_ctx=False)
