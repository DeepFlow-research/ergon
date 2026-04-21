"""Test double for ``SandboxEventSink`` that records every call.

Used by tests that need to assert on the sandbox lifecycle events emitted by
``BaseSandboxManager`` subclasses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class SandboxCreatedCall:
    run_id: UUID
    task_id: UUID
    sandbox_id: str
    timeout_minutes: int
    template: str | None


@dataclass
class SandboxCommandCall:
    run_id: UUID
    task_id: UUID
    sandbox_id: str
    command: str
    stdout: str | None
    stderr: str | None
    exit_code: int | None
    duration_ms: int | None


@dataclass
class SandboxClosedCall:
    task_id: UUID
    sandbox_id: str
    reason: str


@dataclass
class RecordingSandboxEventSink:
    """Test double that records every sink call for assertion."""

    created: list[SandboxCreatedCall] = field(default_factory=list)
    commands: list[SandboxCommandCall] = field(default_factory=list)
    closed: list[SandboxClosedCall] = field(default_factory=list)

    async def sandbox_created(  # slopcop: ignore[max-function-params]
        self,
        run_id: UUID,
        task_id: UUID,
        sandbox_id: str,
        timeout_minutes: int,
        template: str | None = None,
    ) -> None:
        self.created.append(
            SandboxCreatedCall(run_id, task_id, sandbox_id, timeout_minutes, template)
        )

    async def sandbox_command(  # slopcop: ignore[max-function-params]
        self,
        run_id: UUID,
        task_id: UUID,
        sandbox_id: str,
        command: str,
        stdout: str | None = None,
        stderr: str | None = None,
        exit_code: int | None = None,
        duration_ms: int | None = None,
    ) -> None:
        self.commands.append(
            SandboxCommandCall(
                run_id, task_id, sandbox_id, command, stdout, stderr, exit_code, duration_ms
            )
        )

    async def sandbox_closed(
        self,
        task_id: UUID,
        sandbox_id: str,
        reason: str,
    ) -> None:
        self.closed.append(SandboxClosedCall(task_id, sandbox_id, reason))
