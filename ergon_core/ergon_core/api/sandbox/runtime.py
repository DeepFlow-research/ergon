"""Protocol for live sandbox runtime backends."""

from typing import Any, Protocol


class SandboxRuntime(Protocol):
    """Live backing object used by `Sandbox` IO proxies."""

    sandbox_id: str

    async def run_command(
        self,
        command: str,
        timeout: int = 30,
    ) -> Any:  # slopcop: ignore[no-typing-any]
        """Run a command in the live sandbox."""

    async def write_file(self, path: str, content: bytes) -> None:
        """Write bytes to a sandbox path."""

    async def read_file(self, path: str) -> bytes:
        """Read bytes from a sandbox path."""

    async def list_files(self, path: str) -> list[str]:
        """List files below a sandbox path."""
