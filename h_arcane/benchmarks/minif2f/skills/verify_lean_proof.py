"""Verify Lean proof skill - verifies complete proofs (no sorry allowed)."""

import asyncio
from pathlib import Path

from .responses import LeanVerificationResponse


async def main(filename: str) -> LeanVerificationResponse:
    """
    Verify a complete Lean proof (no `sorry` allowed).

    Use this for final verification after developing the proof.
    For iterative development, use write_lean_file + check_lean_file instead.

    Args:
        filename: Name of the Lean file to verify

    Returns:
        LeanVerificationResponse with verified status and any errors
    """
    try:
        filepath = Path("/workspace") / filename
        if not filepath.exists():
            return LeanVerificationResponse(
                success=False,
                verified=False,
                error=f"File not found: {filepath}",
            )

        # Read the file content
        proof_code = filepath.read_text(encoding="utf-8")

        # Check for sorry - not allowed in final verification
        if "sorry" in proof_code:
            return LeanVerificationResponse(
                success=True,
                verified=False,
                message="Proof contains 'sorry' - incomplete proof not allowed for verification",
            )

        # Run Lean compiler with --check flag using subprocess (we're inside sandbox)
        # Note: Lean installation check should be done before calling this tool
        cmd = f"export PATH=$HOME/.elan/bin:$PATH && cd /workspace && lean --check {filename} 2>&1"
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=60)
        output = stdout.decode("utf-8", errors="replace")
        verified = process.returncode == 0

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

    except asyncio.TimeoutError:
        return LeanVerificationResponse(
            success=False,
            verified=False,
            error="Lean verification timed out (>60s)",
        )

    except Exception as e:
        return LeanVerificationResponse(
            success=False,
            verified=False,
            error=f"Error verifying Lean proof: {str(e)}",
        )
