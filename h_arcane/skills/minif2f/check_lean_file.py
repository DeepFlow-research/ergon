"""Check Lean file skill - checks for errors and remaining goals."""

import asyncio
from pathlib import Path

from .responses import LeanCheckResponse
from ._utils import parse_lean_output


async def main(filename: str) -> LeanCheckResponse:
    """
    Check a Lean file for errors and remaining goals.

    This is useful for iterative proof development:
    - Shows compilation errors if syntax/type errors exist
    - Shows remaining goals from `sorry` placeholders
    - Allows partial proofs to type-check

    Args:
        filename: Name of the Lean file to check

    Returns:
        LeanCheckResponse with compiled status, errors, and goals_remaining
    """
    try:
        filepath = Path("/workspace") / filename
        if not filepath.exists():
            return LeanCheckResponse(
                success=False,
                compiled=False,
                errors=[f"File not found: {filepath}"],
            )

        # Run Lean compiler using subprocess (we're inside sandbox)
        # Note: Lean installation check should be done before calling this tool
        cmd = f"export PATH=$HOME/.elan/bin:$PATH && cd /workspace && lean {filename} 2>&1"
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=60)
        output = stdout.decode("utf-8", errors="replace")
        exit_code = process.returncode

        # Parse output
        errors, goals = parse_lean_output(output)

        # File compiled if exit code is 0 OR if it has sorry (partial proof)
        compiled = exit_code == 0 or "sorry" in output

        return LeanCheckResponse(
            success=True,
            compiled=compiled,
            errors=errors if errors else None,
            goals_remaining=goals if goals else None,
        )

    except asyncio.TimeoutError:
        return LeanCheckResponse(
            success=False,
            compiled=False,
            errors=["Lean compilation timed out (>60s)"],
        )

    except Exception as e:
        return LeanCheckResponse(
            success=False,
            compiled=False,
            errors=[f"Error checking Lean file: {str(e)}"],
        )

