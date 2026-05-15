"""Runtime tool construction for MiniF2FToolkit.

Kept in a sibling module so ``MiniF2FToolkit`` (in ``minif2f.py``) remains
serializable: the Pydantic BaseModel carries only config; ``build_tools``
constructs live ``pydantic_ai.tools.Tool`` instances bound to the sandbox.

Import note: ``MiniF2FToolkit`` is only imported under ``TYPE_CHECKING`` to
break the runtime cycle ``minif2f.py → _minif2f_tools.py → minif2f.py``.
# reason: circular import — minif2f.py imports build_tools from this module;
#         importing MiniF2FToolkit at runtime would re-enter minif2f.py
#         before it finishes loading.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field
from pydantic_ai.tools import Tool

from ergon_builtins.benchmarks.minif2f.constants import LEAN_CMD, LEAN_CMD_PREFIX

if TYPE_CHECKING:
    from ergon_builtins.toolkits.minif2f import MiniF2FToolkit

# TODO: we need to break these down into modules so we dont have helpers, core logic and response models in the same file.

# ── Response models ────────────────────────────────────────────────────


class WriteLeanResponse(BaseModel):
    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if failed")
    filename: str | None = Field(default=None, description="Path to the written file")
    bytes_written: int | None = Field(default=None, description="Number of bytes written")


class LeanCheckResponse(BaseModel):
    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if failed")
    compiled: bool = Field(default=False, description="Whether the file compiled (sorry allowed)")
    errors: list[str] | None = Field(default=None, description="Compilation errors if any")
    goals_remaining: list[str] | None = Field(
        default=None, description="Goals from sorry placeholders"
    )
    warnings: list[str] | None = Field(default=None, description="Compiler warnings")


class LeanVerificationResponse(BaseModel):
    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if failed")
    verified: bool = Field(default=False, description="Whether the proof compiled with no sorry")
    message: str | None = Field(default=None, description="Verification result message")
    output: str | None = Field(default=None, description="Lean compiler output")


class SearchLemmasResponse(BaseModel):
    success: bool = Field(description="Whether the search completed successfully")
    error: str | None = Field(default=None, description="Error message if search failed")
    query: str | None = Field(default=None, description="The Lean query that was executed")
    output: str | None = Field(default=None, description="Lean output for the query")


# ── Builder ────────────────────────────────────────────────────────────


def build_tools(  # noqa: C901  # slopcop: ignore[max-function-params]
    toolkit: MiniF2FToolkit,
    *,
    sandbox: Any,  # slopcop: ignore[no-typing-any]
    task: Any,  # slopcop: ignore[no-typing-any]
) -> list[Tool]:
    """Build live pydantic_ai Tool instances bound to the v2 Sandbox."""

    proof_output_path = toolkit.proof_output_path
    lean_workspace = toolkit.lean_workspace

    async def write_lean_file(file_path: str, content: str) -> WriteLeanResponse:
        """Write or update a Lean proof file.

        Use ``sorry`` as a placeholder for incomplete proofs.

        Args:
            file_path: Full path to the file.
                /workspace/scratchpad/draft.lean for drafts.
                /workspace/final_output/final_solution.lean for final submission.
            content: Complete Lean file content.
        """
        try:
            payload = content.encode("utf-8") if isinstance(content, str) else content
            await sandbox.write_file(file_path, payload)
            return WriteLeanResponse(success=True, filename=file_path, bytes_written=len(payload))
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            return WriteLeanResponse(success=False, error=str(exc))

    async def check_lean_file(file_path: str) -> LeanCheckResponse:
        """Check a Lean file for errors and get proof goals.

        Args:
            file_path: Full path to the Lean file to check.
        """
        try:
            cmd = f"{LEAN_CMD_PREFIX} {LEAN_CMD} {file_path} 2>&1"
            result = await sandbox.run_command(cmd, timeout=60)
            output = (result.stdout or "") + (result.stderr or "")
            errors, goals = _parse_lean_output(output)
            compiled = result.exit_code == 0 or "sorry" in output
            return LeanCheckResponse(
                success=True,
                compiled=compiled,
                errors=errors or None,
                goals_remaining=goals or None,
            )
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            return LeanCheckResponse(success=False, error=f"Error checking Lean file: {exc}")

    async def verify_lean_proof(file_path: str) -> LeanVerificationResponse:
        """Verify a complete Lean proof (no ``sorry`` allowed).

        Args:
            file_path: Full path to the Lean file to verify.
        """
        try:
            file_bytes = await sandbox.read_file(file_path)
            file_content = (
                file_bytes.decode("utf-8") if isinstance(file_bytes, bytes) else file_bytes
            )
            if "sorry" in file_content:
                return LeanVerificationResponse(
                    success=True,
                    verified=False,
                    message="Proof contains 'sorry' — incomplete proof not allowed for verification",
                )
            cmd = f"{LEAN_CMD_PREFIX} {LEAN_CMD} {file_path} 2>&1"
            result = await sandbox.run_command(cmd, timeout=60)
            output = (result.stdout or "") + (result.stderr or "")
            verified = result.exit_code == 0
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

    async def search_lemmas(query: str) -> SearchLemmasResponse:
        """Search for lemmas, definitions, or check types in Mathlib.

        Examples:
            search_lemmas("#check mul_comm")
            search_lemmas("#check @finset.sum")
            search_lemmas("#print mul_comm")

        Args:
            query: A Lean query like ``#check lemma_name`` or ``#print lemma_name``.
        """
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
            temp_path = f"{lean_workspace}/src/_search_query.lean"
            await sandbox.write_file(temp_path, lean_content.encode("utf-8"))
            cmd = f"{LEAN_CMD_PREFIX} {LEAN_CMD} src/_search_query.lean 2>&1"
            result = await sandbox.run_command(cmd, timeout=30)
            output = (result.stdout or "") + (result.stderr or "")
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
            return SearchLemmasResponse(success=False, query=query, error=f"Error searching: {exc}")

    return [
        Tool(function=write_lean_file, takes_ctx=False),
        Tool(function=check_lean_file, takes_ctx=False),
        Tool(function=verify_lean_proof, takes_ctx=False),
        Tool(function=search_lemmas, takes_ctx=False),
    ]


# ── Helpers ────────────────────────────────────────────────────────────


def _parse_lean_output(output: str) -> tuple[list[str], list[str]]:
    """Parse Lean compiler output into (errors, goals_remaining)."""
    errors: list[str] = []
    goals: list[str] = []
    error_pattern = re.compile(r"^.*:\d+:\d+:\s*(error|warning):\s*(.+)$")
    goal_pattern = re.compile(r"⊢\s*(.+)$")
    current_error: list[str] = []
    in_error = False
    for raw_line in output.split("\n"):
        line = raw_line.strip()
        if error_pattern.match(line):
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
