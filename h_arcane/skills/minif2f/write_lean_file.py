"""Write Lean file skill - creates or updates Lean proof files."""

from pathlib import Path

from .responses import WriteLeanResponse


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
        filepath = Path("/workspace") / filename
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

