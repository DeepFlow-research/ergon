"""Pydantic response models for smoke test stub tools."""

from pydantic import BaseModel


class StubReadFileResponse(BaseModel):
    """Response from stub read_file tool."""

    success: bool = True
    content: str = ""
    size_bytes: int = 0
    error: str | None = None


class StubWriteFileResponse(BaseModel):
    """Response from stub write_file tool."""

    success: bool = True
    path: str = ""
    size_bytes: int = 0
    error: str | None = None


class StubAnalyzeResponse(BaseModel):
    """Response from stub analyze_data tool."""

    success: bool = True
    summary: str = ""
    findings: list[str] = []
    error: str | None = None
