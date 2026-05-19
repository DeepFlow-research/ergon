"""GDPEval tool response models."""

from pydantic import BaseModel


class BashResponse(BaseModel):
    exit_code: int
    stdout: str
    stderr: str


class EditorResponse(BaseModel):
    ok: bool
    output: str | None = None
    error: str | None = None


class RunPythonResponse(BaseModel):
    ok: bool
    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None
    error: str | None = None


__all__ = ["BashResponse", "EditorResponse", "RunPythonResponse"]
