"""Sandboxed bash tool for manager agents.

Provides a bash callable that runs commands inside the manager's E2B
sandbox. Primary use case: `sleep N` between subtask-status polls.
Also supports light inspection (cat, echo, grep).

This is a separate module (not inline in the toolkit) because it has
no dependency on the subtask lifecycle services --- it only needs the
sandbox_id. Other toolkits can reuse it independently.
"""

from collections.abc import Awaitable, Callable

from ergon_core.api.json_types import JsonObject


async def _stub_sandbox_exec(*, sandbox_id: str, command: str, timeout_s: int) -> dict[str, str]:
    """Stub until sandbox management module exists."""
    raise NotImplementedError(
        f"Sandbox exec not yet wired (sandbox_id={sandbox_id}, command={command!r})"
    )


def make_sandbox_bash_tool(*, sandbox_id: str) -> Callable[..., Awaitable[JsonObject]]:
    """Produce a single bash callable bound to the given sandbox."""

    async def bash(command: str, timeout_s: int = 30) -> JsonObject:
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
            return {
                "success": True,
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "exit_code": result.get("exit_code", 0),
            }
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            return {"success": False, "error": str(exc)}

    return bash
