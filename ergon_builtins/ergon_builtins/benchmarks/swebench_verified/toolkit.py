"""Tools exposed to a SWE-Bench worker.

Deliberately generic: one bash tool and one str-replace editor. Enough to
solve the benchmark end-to-end and portable to other code-editing tasks.
"""

import shlex
from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel
from pydantic_ai.tools import Tool


class BashResponse(BaseModel):
    exit_code: int
    stdout: str
    stderr: str


class EditorResponse(BaseModel):
    ok: bool
    output: str | None = None
    error: str | None = None


class SWEBenchToolkit:
    def __init__(
        self,
        *,
        sandbox: Any,  # slopcop: ignore[no-typing-any]
        workdir: str = "/workspace/repo",
    ) -> None:
        self._sandbox = sandbox
        self._workdir = workdir

    def get_tools(self) -> Sequence[Tool]:
        return [self._bash_tool(), self._editor_tool()]

    def _bash_tool(self) -> Tool:
        async def bash(command: str, timeout_sec: int = 300) -> BashResponse:
            """Run a shell command inside the repo workdir."""
            wrapped = f"cd {shlex.quote(self._workdir)} && {command}"
            result = await self._sandbox.commands.run(wrapped, timeout=timeout_sec)
            return BashResponse(
                exit_code=result.exit_code,
                stdout=result.stdout or "",
                stderr=getattr(result, "stderr", "") or "",  # slopcop: ignore[no-hasattr-getattr]
            )

        return Tool(function=bash, takes_ctx=False, name="bash")

    def _editor_tool(self) -> Tool:
        async def str_replace_editor(
            command: Literal["view", "create", "str_replace"],
            path: str,
            file_text: str | None = None,
            old_str: str | None = None,
            new_str: str | None = None,
        ) -> EditorResponse:
            """View, create, or edit a file by exact string replacement."""
            abs_path = f"{self._workdir.rstrip('/')}/{path.lstrip('/')}"
            try:
                if command == "view":
                    content = await self._sandbox.files.read(abs_path)
                    return EditorResponse(ok=True, output=content)

                if command == "create":
                    if file_text is None:
                        return EditorResponse(ok=False, error="file_text required for create")
                    await self._sandbox.files.write(abs_path, file_text.encode())
                    return EditorResponse(ok=True, output=f"created {abs_path}")

                if command == "str_replace":
                    if old_str is None or new_str is None:
                        return EditorResponse(ok=False, error="old_str and new_str required")
                    content = await self._sandbox.files.read(abs_path)
                    occurrences = content.count(old_str)
                    if occurrences == 0:
                        return EditorResponse(ok=False, error="old_str not found")
                    if occurrences > 1:
                        return EditorResponse(
                            ok=False,
                            error=f"old_str not unique ({occurrences} matches); add more context",
                        )
                    new_content = content.replace(old_str, new_str, 1)
                    await self._sandbox.files.write(abs_path, new_content.encode())
                    return EditorResponse(ok=True, output=f"edited {abs_path}")

                return EditorResponse(ok=False, error=f"unknown command {command!r}")
            except Exception as exc:  # slopcop: ignore[no-broad-except]
                return EditorResponse(ok=False, error=str(exc))

        return Tool(function=str_replace_editor, takes_ctx=False, name="str_replace_editor")
