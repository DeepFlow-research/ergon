"""Response models for formal math tools."""

import sys
from pydantic import Field

# Import based on execution context
if "/tools" in sys.path or any("/tools" in p for p in sys.path):
    # Running in sandbox - /tools is in sys.path
    from responses import ToolResponse  # type: ignore[import-untyped]
else:
    # Running locally - use full import path
    from h_arcane.tools.responses import ToolResponse


class WriteLeanResponse(ToolResponse):
    """Response from write_lean_file tool."""

    filename: str | None = Field(default=None, description="Path to the written file")
    bytes_written: int | None = Field(default=None, description="Number of bytes written")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "filename": "/workspace/proof.lean",
                "bytes_written": 256,
                "error": None,
            }
        }


class LeanCheckResponse(ToolResponse):
    """Response from check_lean_file - includes goal information for iterative development."""

    compiled: bool = Field(default=False, description="Whether the file compiled (sorry allowed)")
    errors: list[str] | None = Field(default=None, description="Compilation errors if any")
    goals_remaining: list[str] | None = Field(
        default=None, description="Goals from sorry placeholders"
    )
    warnings: list[str] | None = Field(default=None, description="Compiler warnings")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "compiled": True,
                "errors": None,
                "goals_remaining": ["⊢ 1 + 1 = 2"],
                "warnings": None,
            }
        }


class LeanVerificationResponse(ToolResponse):
    """Response from verify_lean_proof - final pass/fail (no sorry allowed)."""

    verified: bool = Field(
        default=False,
        description="Whether the proof compiled and verified",
    )
    errors: str | None = Field(
        default=None, description="Compilation/verification errors if failed"
    )
    output: str | None = Field(default=None, description="Lean compiler output")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "verified": True,
                "errors": None,
                "output": "theorem example verified",
            }
        }
