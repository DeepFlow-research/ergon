"""MiniF2F tool response models."""

from pydantic import BaseModel, Field


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


__all__ = [
    "LeanCheckResponse",
    "LeanVerificationResponse",
    "SearchLemmasResponse",
    "WriteLeanResponse",
]
