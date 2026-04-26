"""Sandboxed bash tool for manager agents.

Provides a bash callable that runs commands inside the manager's E2B
sandbox. Primary use case: `sleep N` between subtask-status polls.
Also supports light inspection (cat, echo, grep).

This is a separate module (not inline in the toolkit) because it has
no dependency on the subtask lifecycle services --- it only needs the
sandbox_id. Other toolkits can reuse it independently.
"""

from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel


class BashToolSuccess(BaseModel):
    kind: Literal["success"] = "success"
    stdout: str
    stderr: str
    exit_code: int

    model_config = {"frozen": True}


class BashToolFailure(BaseModel):
    kind: Literal["failure"] = "failure"
    error: str

    model_config = {"frozen": True}


type BashToolResponse = BashToolSuccess | BashToolFailure


class SandboxExecResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int


async def _stub_sandbox_exec(*, sandbox_id: str, command: str, timeout_s: int) -> SandboxExecResult:
    """Stub until sandbox management module exists."""
    raise NotImplementedError(
        f"Sandbox exec not yet wired (sandbox_id={sandbox_id}, command={command!r})"
    )


def make_sandbox_bash_tool(*, sandbox_id: str) -> Callable[..., Awaitable[BashToolResponse]]:
    """Produce a single bash callable bound to the given sandbox."""

    async def bash(command: str, timeout_s: int = 30) -> BashToolResponse:
        """Run a shell command inside the manager's sandbox. Useful for:
        - `sleep 10` between subtask-status polls;
        - `cat` / `echo` for light inspection;
        - simple pipes (grep / awk).
        No host-filesystem access; network policy is inherited from the sandbox."""
        try:
            result = await _stub_sandbox_exec(
                sandbox_id=sandbox_id,
                command=command,
                timeout_s=timeout_s,
            )
            return BashToolSuccess(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.exit_code,
            )
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            return BashToolFailure(error=str(exc))

    return bash
