"""Public Protocol for the criterion runtime + its small result DTOs.

``CriterionRuntime`` is the capabilities surface criteria use to interact
with the sandbox and LLM judge while they evaluate.  Lives in ``api/`` so
that ``EvaluationContext`` (also in ``api/``) can type it without dragging
in the core runtime package (which would cause a circular import).
"""

from typing import Protocol, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)

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
    """Execution surface injected into a ``Criterion`` at evaluation time.

    The runtime owns the sandbox lifecycle (create / reset timeout /
    cleanup) on behalf of the criterion and exposes a small set of
    primitives the criterion calls to gather evidence.  A criterion that
    doesn't need sandbox access or a judge simply ignores it.
    """

    async def ensure_sandbox(self) -> None: ...
    async def upload_files(self, files: list[dict]) -> None: ...
    async def write_file(self, path: str, content: bytes) -> None: ...
    async def run_command(self, command: str, timeout: int = 30) -> CommandResult: ...
    async def execute_code(self, code: str) -> SandboxResult: ...
    async def call_llm_judge(self, messages: list, response_type: type[T]) -> T: ...
    async def cleanup(self) -> None: ...
