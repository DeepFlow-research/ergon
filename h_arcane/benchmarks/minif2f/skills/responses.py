"""Pydantic response models for MiniF2F Lean skills.

These models are used both in the VM (by skills) and locally (by toolkits).
Uses relative imports in skills, absolute imports in toolkits.
"""

from pydantic import BaseModel, Field


class WriteLeanResponse(BaseModel):
    """Response from write_lean_file skill."""

    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    filename: str | None = Field(default=None, description="Path to the written file")
    bytes_written: int | None = Field(default=None, description="Number of bytes written")


class LeanCheckResponse(BaseModel):
    """Response from check_lean_file skill - includes goal information for iterative development."""

    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    compiled: bool = Field(default=False, description="Whether the file compiled (sorry allowed)")
    errors: list[str] | None = Field(default=None, description="Compilation errors if any")
    goals_remaining: list[str] | None = Field(
        default=None, description="Goals from sorry placeholders"
    )
    warnings: list[str] | None = Field(default=None, description="Compiler warnings")


class LeanVerificationResponse(BaseModel):
    """Response from verify_lean_proof skill - final pass/fail (no sorry allowed)."""

    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    verified: bool = Field(
        default=False,
        description="Whether the proof compiled and verified (no sorry)",
    )
    message: str | None = Field(default=None, description="Verification result message")
    output: str | None = Field(default=None, description="Lean compiler output")


class SearchLemmasResponse(BaseModel):
    """Response from search_lemmas - query output or structured failure."""

    success: bool = Field(description="Whether the search completed successfully")
    error: str | None = Field(default=None, description="Error message if the search failed")
    query: str | None = Field(default=None, description="The Lean query that was executed")
    output: str | None = Field(default=None, description="Lean output for the query")
