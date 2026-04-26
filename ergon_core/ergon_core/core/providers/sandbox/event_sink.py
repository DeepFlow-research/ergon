"""Sandbox lifecycle/event sink abstractions."""

from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from ergon_core.core.persistence.shared.db import get_session


@runtime_checkable
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
        run_id: UUID,
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
        run_id: UUID | None = None,
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
        run_id: UUID,
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
        run_id: UUID | None = None,
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
        run_id: UUID,
        task_id: UUID,
        sandbox_id: str,
        command: str,
        stdout: str | None = None,
        stderr: str | None = None,
        exit_code: int | None = None,
        duration_ms: int | None = None,
    ) -> None:
        await self._emitter.sandbox_command(
            run_id=run_id,
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
        run_id: UUID | None = None,
    ) -> None:
        await self._emitter.sandbox_closed(
            task_id=task_id,
            sandbox_id=sandbox_id,
            reason=reason,
        )


class PostgresSandboxEventSink:
    """Persists sandbox lifecycle events and command WAL to Postgres.

    Writes to ``sandbox_events`` and ``sandbox_command_wal_entries``.
    Failures are swallowed with a warning so that a Postgres hiccup never
    blocks sandbox I/O.
    """

    async def sandbox_created(
        self,
        run_id: UUID,
        task_id: UUID,
        sandbox_id: str,
        timeout_minutes: int,
        template: str | None = None,
    ) -> None:
        from ergon_core.core.persistence.telemetry.models import SandboxEvent

        with get_session() as s:
            s.add(
                SandboxEvent(
                    run_id=run_id,
                    task_id=task_id,
                    sandbox_id=sandbox_id,
                    kind="sandbox_created",
                    timeout_minutes=timeout_minutes,
                    template=template,
                )
            )
            s.commit()

    async def sandbox_command(
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
        from ergon_core.core.persistence.telemetry.models import SandboxCommandWalEntry

        with get_session() as s:
            s.add(
                SandboxCommandWalEntry(
                    run_id=run_id,
                    task_id=task_id,
                    sandbox_id=sandbox_id,
                    command=command,
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=exit_code,
                    duration_ms=duration_ms,
                )
            )
            s.commit()

    async def sandbox_closed(
        self,
        task_id: UUID,
        sandbox_id: str,
        reason: str,
        run_id: UUID | None = None,
    ) -> None:
        if run_id is None:
            return
        from ergon_core.core.persistence.telemetry.models import SandboxEvent

        with get_session() as s:
            s.add(
                SandboxEvent(
                    run_id=run_id,
                    task_id=task_id,
                    sandbox_id=sandbox_id,
                    kind="sandbox_closed",
                    reason=reason,
                )
            )
            s.commit()


class CompoundSandboxEventSink:
    """Dispatches to multiple sinks in order.

    Constructed in app lifespan with ``DashboardEmitterSandboxEventSink``
    and ``PostgresSandboxEventSink`` so both paths run on every event.
    Failures in one sink propagate (no swallowing at this level).
    """

    def __init__(self, *sinks: SandboxEventSink) -> None:
        self._sinks = sinks

    async def sandbox_created(
        self,
        run_id: UUID,
        task_id: UUID,
        sandbox_id: str,
        timeout_minutes: int,
        template: str | None = None,
    ) -> None:
        for sink in self._sinks:
            await sink.sandbox_created(
                run_id=run_id,
                task_id=task_id,
                sandbox_id=sandbox_id,
                timeout_minutes=timeout_minutes,
                template=template,
            )

    async def sandbox_command(
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
        for sink in self._sinks:
            await sink.sandbox_command(
                run_id=run_id,
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
        run_id: UUID | None = None,
    ) -> None:
        for sink in self._sinks:
            await sink.sandbox_closed(
                task_id=task_id,
                sandbox_id=sandbox_id,
                reason=reason,
                run_id=run_id,
            )
