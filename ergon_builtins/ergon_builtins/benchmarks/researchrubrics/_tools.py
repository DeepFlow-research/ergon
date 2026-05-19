"""Runtime tool construction for ResearchRubricsToolkit.

Kept in a sibling module so ``ResearchRubricsToolkit`` (in ``toolkit.py``)
remains serializable: the Pydantic BaseModel carries only config;
``build_tools`` constructs live ``pydantic_ai.tools.Tool`` instances bound
to the sandbox.

Import note: ``ResearchRubricsToolkit`` is only imported under
``TYPE_CHECKING`` to break the runtime cycle ``toolkit.py → _tools.py →
toolkit.py``.
# reason: circular import — toolkit.py imports build_tools from this module;
#         importing ResearchRubricsToolkit at runtime would re-enter
#         toolkit.py before it finishes loading.
"""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel
from pydantic_ai.tools import Tool

if TYPE_CHECKING:
    from ergon_builtins.benchmarks.researchrubrics.toolkit import ResearchRubricsToolkit


# ── Response models ────────────────────────────────────────────────────


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


# ── Builder ────────────────────────────────────────────────────────────


def build_tools(
    toolkit: ResearchRubricsToolkit,
    *,
    sandbox: Any,  # slopcop: ignore[no-typing-any]
    task: Any,  # slopcop: ignore[no-typing-any]
) -> list[Tool]:
    """Build live pydantic_ai Tool instances bound to the v2 Sandbox.

    Tools provided:

    - ``bash`` — run shell commands in the research sandbox workdir
    - ``write_report`` — write a markdown report draft under
      ``/workspace/final_output``
    - ``read_report`` — read back a previously-written report

    This factory is the v2 entry point invoked by ``ReActWorker.execute``
    when the benchmark's serializable toolkit is attached to the task.
    """

    workdir = toolkit.workspace_root

    async def bash(command: str, timeout_sec: int = 300) -> BashResult:
        """Run a shell command inside the research workdir."""
        wrapped = f"cd {shlex.quote(workdir)} && {command}"
        result = await sandbox.run_command(wrapped, timeout=timeout_sec)
        stdout = "" if result.stdout is None else result.stdout
        stderr = "" if result.stderr is None else result.stderr
        return BashResult(
            exit_code=result.exit_code,
            stdout=stdout,
            stderr=stderr,
        )

    async def write_report(relative_path: str, content: str) -> ReportWriteResult:
        """Write a markdown report under ``/workspace/<relative_path>``."""
        cleaned = relative_path.lstrip("/")
        if ".." in cleaned.split("/"):
            return ReportWriteResult(
                ok=False,
                path=relative_path,
                error=f"path escapes /workspace: {relative_path!r}",
            )
        abs_path = f"{workdir.rstrip('/')}/{cleaned}"
        try:
            payload = content.encode("utf-8")
            await sandbox.write_file(abs_path, payload)
            return ReportWriteResult(ok=True, path=abs_path, bytes_written=len(payload))
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            return ReportWriteResult(ok=False, path=abs_path, error=str(exc))

    async def read_report(relative_path: str) -> ReportReadResult:
        """Read a previously-written report under ``/workspace/<relative_path>``."""
        cleaned = relative_path.lstrip("/")
        if ".." in cleaned.split("/"):
            return ReportReadResult(
                ok=False,
                path=relative_path,
                error=f"path escapes /workspace: {relative_path!r}",
            )
        abs_path = f"{workdir.rstrip('/')}/{cleaned}"
        try:
            raw = await sandbox.read_file(abs_path)
            text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            return ReportReadResult(ok=True, path=abs_path, content=text)
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            return ReportReadResult(ok=False, path=abs_path, error=str(exc))

    return [
        Tool(function=bash, takes_ctx=False, name="bash"),
        Tool(function=write_report, takes_ctx=False, name="write_report"),
        Tool(function=read_report, takes_ctx=False, name="read_report"),
    ]
