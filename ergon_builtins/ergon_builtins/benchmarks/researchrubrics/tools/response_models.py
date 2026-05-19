"""ResearchRubrics tool response models."""

from pydantic import BaseModel


class ReportWriteResult(BaseModel):
    ok: bool
    path: str
    bytes_written: int | None = None
    error: str | None = None


class ReportReadResult(BaseModel):
    ok: bool
    path: str
    content: str | None = None
    error: str | None = None


class BashResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str


__all__ = ["BashResult", "ReportReadResult", "ReportWriteResult"]
