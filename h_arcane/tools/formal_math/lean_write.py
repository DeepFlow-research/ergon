"""Write Lean file tool - works in sandbox."""

import sys
from pathlib import Path

# Import based on execution context
if "/tools" in sys.path or any("/tools" in p for p in sys.path):
    # Running in sandbox - /tools is in sys.path
    from formal_math.responses import WriteLeanResponse  # type: ignore[import-untyped]
else:
    # Running locally - use full import path
    from h_arcane.tools.formal_math.responses import WriteLeanResponse


async def write_lean_file(filename: str, content: str) -> WriteLeanResponse:
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

    Example:
        ```python
        result = await write_lean_file(
            filename="proof.lean",
            content="theorem example : 1 + 1 = 2 := by sorry"
        )
        if result.success:
            print(f"Wrote {result.bytes_written} bytes to {result.filename}")
        ```
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
            error=None,
        )
    except Exception as e:
        return WriteLeanResponse(
            success=False,
            filename=None,
            bytes_written=None,
            error=f"Error writing Lean file: {str(e)}",
        )
