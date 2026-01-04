"""Write Lean file skill - creates or updates Lean proof files."""

from pathlib import Path

from .responses import WriteLeanResponse

# Write files inside the Mathlib project so they have access to Mathlib imports
# NOTE: Mathlib is installed in /tools (not /workspace) to avoid downloading all library
# files as outputs when the run completes.
LEAN_PROJECT_SRC = Path("/tools/mathlib_project/src")


async def main(filename: str, content: str) -> WriteLeanResponse:
    """
    Write or update a Lean proof file. Use this to build proofs incrementally.

    Use `sorry` as a placeholder to mark incomplete parts:

    theorem example : 1 + 1 = 2 := by
      sorry  -- Placeholder, check_lean_file will show the goal

    Args:
        filename: Name of the Lean file (e.g., "proof.lean")
        content: Complete Lean file content

    Returns:
        WriteLeanResponse with filename and bytes written
    """
    try:
        # Ensure Mathlib project src directory exists
        LEAN_PROJECT_SRC.mkdir(parents=True, exist_ok=True)

        filepath = LEAN_PROJECT_SRC / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)

        content_bytes = content.encode("utf-8")
        filepath.write_bytes(content_bytes)

        return WriteLeanResponse(
            success=True,
            filename=str(filepath),
            bytes_written=len(content_bytes),
        )

    except Exception as e:
        return WriteLeanResponse(
            success=False,
            error=f"Error writing Lean file: {str(e)}",
        )
