"""Criterion runtime contracts and small sandbox result DTOs."""

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from sqlmodel import Session

    from ergon_core.core.providers.sandbox.event_sink import SandboxEventSink
    from ergon_core.core.runtime.resources import RunResourceView

__all__ = ["CommandResult", "CriterionRuntime", "SandboxResult"]


class SandboxResult(BaseModel):
    """Result from sandbox code execution."""

    stdout: list[str] = Field(
        default_factory=list,
        description="Captured stdout lines from the sandbox process.",
    )
    stderr: list[str] = Field(
        default_factory=list,
        description="Captured stderr lines from the sandbox process.",
    )


class CommandResult(BaseModel):
    """Result from command execution in a sandbox."""

    stdout: str | None = Field(
        default=None,
        description="Captured stdout; ``None`` if the command never produced any.",
    )
    stderr: str | None = Field(
        default=None,
        description="Captured stderr; ``None`` if the command never produced any.",
    )
    exit_code: int | None = Field(
        default=None,
        description="Process exit code; ``None`` if the command could not be started.",
    )


class CriterionRuntime(Protocol):
    """Execution surface injected into a ``Criterion`` at evaluation time."""

    async def ensure_sandbox(self) -> None: ...
    async def upload_files(self, files: list[dict]) -> None: ...
    async def write_file(self, path: str, content: bytes) -> None: ...
    async def run_command(self, command: str, timeout: int = 30) -> CommandResult: ...
    async def execute_code(self, code: str) -> SandboxResult: ...
    async def cleanup(self) -> None: ...

    async def read_resource(self, name: str) -> bytes: ...
    async def read_resource_by_id(self, resource_id: UUID) -> bytes: ...
    async def list_resources(
        self,
        task_execution_id: UUID | None = None,
    ) -> "list[RunResourceView]": ...

    async def get_all_files_for_task(self) -> "dict[str, bytes]":
        """Return ``{name: bytes}`` for every resource produced by this task."""
        ...

    def db_read_session(self) -> "Session": ...
    def event_sink(self) -> "SandboxEventSink": ...
