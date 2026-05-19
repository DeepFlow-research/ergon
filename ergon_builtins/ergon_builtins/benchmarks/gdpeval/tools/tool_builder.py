"""Runtime tool construction for GDPEvalToolkit.

Kept in a sibling module so ``GDPEvalToolkit`` (in ``toolkit.py``) remains
serializable: the Pydantic BaseModel carries only config; ``build_tools``
constructs live ``pydantic_ai.tools.Tool`` instances bound to the sandbox.

Import note: ``GDPEvalToolkit`` is only imported under ``TYPE_CHECKING`` to
break the runtime cycle ``toolkit.py → tools/tool_builder.py → toolkit.py``.
# reason: circular import — toolkit.py imports build_tools from this
#         module; importing GDPEvalToolkit at runtime would re-enter
#         toolkit.py before it finishes loading.
"""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel
from pydantic_ai.tools import Tool

if TYPE_CHECKING:
    from ergon_builtins.benchmarks.gdpeval.toolkit import GDPEvalToolkit


# ── Response models ────────────────────────────────────────────────────


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


# ── Builder ────────────────────────────────────────────────────────────


def build_tools(  # noqa: C901
    toolkit: GDPEvalToolkit,
    *,
    sandbox: Any,  # slopcop: ignore[no-typing-any]
    task: Any,  # slopcop: ignore[no-typing-any]
) -> list[Tool]:
    """Build live pydantic_ai Tool instances bound to the v2 Sandbox.

    Tools provided:

    - ``bash`` — run shell commands inside the workspace
    - ``str_replace_editor`` — view / create / edit files
    - ``run_python`` — run an inline Python snippet inside the sandbox
    """

    workspace = toolkit.scratchpad_dir

    async def bash(command: str, timeout_sec: int = 300) -> BashResponse:
        """Run a shell command inside the workspace scratchpad."""
        wrapped = f"cd {shlex.quote(workspace)} && {command}"
        result = await sandbox.run_command(wrapped, timeout=timeout_sec)
        stdout = "" if result.stdout is None else result.stdout
        stderr = "" if result.stderr is None else result.stderr
        return BashResponse(
            exit_code=result.exit_code,
            stdout=stdout,
            stderr=stderr,
        )

    async def str_replace_editor(
        command: Literal["view", "create", "str_replace"],
        path: str,
        file_text: str | None = None,
        old_str: str | None = None,
        new_str: str | None = None,
    ) -> EditorResponse:
        """View, create, or edit a file by exact string replacement."""
        abs_path = path if path.startswith("/") else f"{workspace.rstrip('/')}/{path.lstrip('/')}"
        try:
            if command == "view":
                content_bytes = await sandbox.read_file(abs_path)
                content = (
                    content_bytes.decode("utf-8")
                    if isinstance(content_bytes, bytes)
                    else content_bytes
                )
                return EditorResponse(ok=True, output=content)

            if command == "create":
                if file_text is None:
                    return EditorResponse(ok=False, error="file_text required for create")
                await sandbox.write_file(abs_path, file_text.encode())
                return EditorResponse(ok=True, output=f"created {abs_path}")

            if command == "str_replace":
                if old_str is None or new_str is None:
                    return EditorResponse(ok=False, error="old_str and new_str required")
                content_bytes = await sandbox.read_file(abs_path)
                content = (
                    content_bytes.decode("utf-8")
                    if isinstance(content_bytes, bytes)
                    else content_bytes
                )
                occurrences = content.count(old_str)
                if occurrences == 0:
                    return EditorResponse(ok=False, error="old_str not found")
                if occurrences > 1:
                    return EditorResponse(
                        ok=False,
                        error=f"old_str not unique ({occurrences} matches); add more context",
                    )
                new_content = content.replace(old_str, new_str, 1)
                await sandbox.write_file(abs_path, new_content.encode())
                return EditorResponse(ok=True, output=f"edited {abs_path}")

            return EditorResponse(ok=False, error=f"unknown command {command!r}")
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            return EditorResponse(ok=False, error=str(exc))

    async def run_python(code: str, timeout_sec: int = 120) -> RunPythonResponse:
        """Execute a Python snippet inside the sandbox via ``python -c``."""
        try:
            wrapped = f"cd {shlex.quote(workspace)} && python -c {shlex.quote(code)}"
            result = await sandbox.run_command(wrapped, timeout=timeout_sec)
            stdout = "" if result.stdout is None else result.stdout
            stderr = "" if result.stderr is None else result.stderr
            return RunPythonResponse(
                ok=result.exit_code == 0,
                stdout=stdout,
                stderr=stderr,
                exit_code=result.exit_code,
            )
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            return RunPythonResponse(ok=False, error=str(exc))

    return [
        Tool(function=bash, takes_ctx=False, name="bash"),
        Tool(function=str_replace_editor, takes_ctx=False, name="str_replace_editor"),
        Tool(function=run_python, takes_ctx=False, name="run_python"),
    ]
