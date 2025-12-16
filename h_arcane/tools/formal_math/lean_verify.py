"""Verify Lean proof tool - works in sandbox."""

import asyncio
import sys
from pathlib import Path

# Import based on execution context
if "/tools" in sys.path or any("/tools" in p for p in sys.path):
    # Running in sandbox - /tools is in sys.path
    from formal_math.responses import LeanVerificationResponse  # type: ignore[import-untyped]
else:
    # Running locally - use full import path
    from h_arcane.tools.formal_math.responses import LeanVerificationResponse


async def verify_lean_proof(proof_code: str) -> LeanVerificationResponse:
    """
    Verify a complete Lean proof (no `sorry` allowed).

    Use this for final verification after developing the proof.
    For iterative development, use write_lean_file + check_lean_file instead.

    Args:
        proof_code: Complete Lean code including theorem statement and proof

    Returns:
        LeanVerificationResponse with verified status and any errors

    Example:
        ```python
        result = await verify_lean_proof(
            "theorem example : 1 + 1 = 2 := by simp"
        )
        if result.verified:
            print("Proof verified!")
        ```
    """
    try:
        # Check for sorry - not allowed in final verification
        if "sorry" in proof_code:
            return LeanVerificationResponse(
                success=True,
                verified=False,
                errors="Proof contains 'sorry' - incomplete proof not allowed for verification",
                output=None,
            )

        # Write proof to temporary file
        verify_file = Path("/workspace") / "verify.lean"
        verify_file.write_text(proof_code, encoding="utf-8")

        # Run Lean compiler with --check flag using subprocess (we're inside sandbox)
        # Note: Lean installation check should be done before calling this tool
        cmd = "export PATH=$HOME/.elan/bin:$PATH && cd /workspace && lean --check verify.lean 2>&1"
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=60)
        output = stdout.decode("utf-8", errors="replace")
        verified = process.returncode == 0

        return LeanVerificationResponse(
            success=True,
            verified=verified,
            errors=output if not verified else None,
            output=output if verified else None,
        )
    except asyncio.TimeoutError:
        return LeanVerificationResponse(
            success=False,
            verified=False,
            errors="Lean verification timed out (>60s)",
            output=None,
        )
    except Exception as e:
        return LeanVerificationResponse(
            success=False,
            verified=False,
            errors=f"Error verifying Lean proof: {str(e)}",
            output=None,
        )
