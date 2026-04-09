"""Sandbox lifecycle/event sink abstractions."""

from typing import Any, Protocol
from uuid import UUID


class SandboxEventSink(Protocol):
    """Observer for sandbox lifecycle and append-only WAL events."""

    async def sandbox_created(
        self,
        run_id: UUID,
        task_id: UUID,
        sandbox_id: str,
        timeout_minutes: int,
        template: str | None = None,
    ) -> None: ...

    async def sandbox_command(
        self,
        task_id: UUID,
        sandbox_id: str,
        command: str,
        stdout: str | None = None,
        stderr: str | None = None,
        exit_code: int | None = None,
        duration_ms: int | None = None,
    ) -> None: ...

    async def sandbox_closed(
        self,
        task_id: UUID,
        sandbox_id: str,
        reason: str,
    ) -> None: ...


class NoopSandboxEventSink:
    """Default observer used when dashboard streaming is unavailable."""

    async def sandbox_created(
        self,
        run_id: UUID,
        task_id: UUID,
        sandbox_id: str,
        timeout_minutes: int,
        template: str | None = None,
    ) -> None:
        return

    async def sandbox_command(
        self,
        task_id: UUID,
        sandbox_id: str,
        command: str,
        stdout: str | None = None,
        stderr: str | None = None,
        exit_code: int | None = None,
        duration_ms: int | None = None,
    ) -> None:
        return

    async def sandbox_closed(
        self,
        task_id: UUID,
        sandbox_id: str,
        reason: str,
    ) -> None:
        return


class DashboardEmitterSandboxEventSink:
    """Adapter that forwards sandbox events to the dashboard emitter."""

    def __init__(self, emitter: Any):  # slopcop: ignore[no-typing-any]
        self._emitter = emitter

    async def sandbox_created(
        self,
        run_id: UUID,
        task_id: UUID,
        sandbox_id: str,
        timeout_minutes: int,
        template: str | None = None,
    ) -> None:
        await self._emitter.sandbox_created(
            run_id=run_id,
            task_id=task_id,
            sandbox_id=sandbox_id,
            timeout_minutes=timeout_minutes,
            template=template,
        )

    async def sandbox_command(
        self,
        task_id: UUID,
        sandbox_id: str,
        command: str,
        stdout: str | None = None,
        stderr: str | None = None,
        exit_code: int | None = None,
        duration_ms: int | None = None,
    ) -> None:
        await self._emitter.sandbox_command(
            task_id=task_id,
            sandbox_id=sandbox_id,
            command=command,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=duration_ms,
        )

    async def sandbox_closed(
        self,
        task_id: UUID,
        sandbox_id: str,
        reason: str,
    ) -> None:
        await self._emitter.sandbox_closed(
            task_id=task_id,
            sandbox_id=sandbox_id,
            reason=reason,
        )
