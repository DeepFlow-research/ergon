"""Instrumented sandbox proxy that emits events via SandboxEventSink."""

from __future__ import annotations  # slopcop: ignore[no-future-annotations]

import time
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from e2b_code_interpreter import AsyncSandbox  # type: ignore[import-untyped]
    from e2b.sandbox_async.commands.command import Commands  # type: ignore[import-untyped]
    from e2b.sandbox_async.filesystem.filesystem import Filesystem  # type: ignore[import-untyped]

try:
    from e2b.sandbox.commands.command_handle import (
        CommandExitException,  # type: ignore[import-untyped]
    )
except ImportError:
    CommandExitException = Exception  # type: ignore[assignment,misc]

from ergon_core.core.providers.sandbox.event_sink import SandboxEventSink
from ergon_core.core.providers.sandbox.utils import (
    _truncate,
    bytes_length,
    coerce_text,
    preview_python_code,
)


class InstrumentedSandboxCommands:
    """Proxy around sandbox shell commands that emits events via the sink."""

    def __init__(
        self,
        sink: SandboxEventSink,
        run_id: UUID,
        task_id: UUID,
        sandbox_id: str,
        commands: Commands,
        max_output_len: int = 4000,
    ):
        self._sink = sink
        self._run_id = run_id
        self._task_id = task_id
        self._sandbox_id = sandbox_id
        self._commands = commands
        self._max_output_len = max_output_len

    async def _emit(
        self,
        command: str,
        started_at: float,
        stdout: str | None = None,
        stderr: str | None = None,
        exit_code: int | None = 0,
    ) -> None:
        duration_ms = int((time.time() - started_at) * 1000)
        await self._sink.sandbox_command(
            run_id=self._run_id,
            task_id=self._task_id,
            sandbox_id=self._sandbox_id,
            command=_truncate(command, 512) or command,
            stdout=_truncate(coerce_text(stdout), self._max_output_len),
            stderr=_truncate(coerce_text(stderr), self._max_output_len),
            exit_code=exit_code,
            duration_ms=duration_ms,
        )

    async def run(self, command: str, *args: object, **kwargs: object) -> object:
        started_at = time.time()
        try:
            result = await self._commands.run(command, *args, **kwargs)
            await self._emit(
                command,
                started_at,
                stdout=coerce_text(
                    getattr(result, "stdout", None)  # slopcop: ignore[no-hasattr-getattr]
                ),
                stderr=coerce_text(
                    getattr(result, "stderr", None)  # slopcop: ignore[no-hasattr-getattr]
                ),
                exit_code=getattr(result, "exit_code", 0),  # slopcop: ignore[no-hasattr-getattr]
            )
            return result
        except CommandExitException as exc:
            await self._emit(
                command,
                started_at,
                stdout=coerce_text(exc.stdout),
                stderr=coerce_text(exc.stderr),
                exit_code=exc.exit_code,
            )
            raise
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            await self._emit(command, started_at, stderr=str(exc), exit_code=1)
            raise

    def __getattr__(self, name: str) -> object:
        return getattr(self._commands, name)  # slopcop: ignore[no-hasattr-getattr]


class InstrumentedSandboxFiles:
    """Proxy around sandbox file operations that emits events via the sink."""

    def __init__(
        self,
        sink: SandboxEventSink,
        run_id: UUID,
        task_id: UUID,
        sandbox_id: str,
        files: Filesystem,
        max_output_len: int = 4000,
    ):
        self._sink = sink
        self._run_id = run_id
        self._task_id = task_id
        self._sandbox_id = sandbox_id
        self._files = files
        self._max_output_len = max_output_len

    async def _emit(
        self,
        command: str,
        started_at: float,
        stdout: str | None = None,
        stderr: str | None = None,
        exit_code: int | None = 0,
    ) -> None:
        duration_ms = int((time.time() - started_at) * 1000)
        await self._sink.sandbox_command(
            run_id=self._run_id,
            task_id=self._task_id,
            sandbox_id=self._sandbox_id,
            command=command,
            stdout=_truncate(stdout, self._max_output_len),
            stderr=_truncate(stderr, self._max_output_len),
            exit_code=exit_code,
            duration_ms=duration_ms,
        )

    async def write(self, path: str, content: object, *args: object, **kwargs: object) -> object:
        started_at = time.time()
        size_bytes = bytes_length(content)
        try:
            result = await self._files.write(path, content, *args, **kwargs)
            stdout = f"{size_bytes} bytes written" if size_bytes is not None else None
            await self._emit(f"file.write: {path}", started_at, stdout=stdout)
            return result
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            await self._emit(f"file.write: {path}", started_at, stderr=str(exc), exit_code=1)
            raise

    async def read(self, path: str, *args: object, **kwargs: object) -> object:
        started_at = time.time()
        try:
            result = await self._files.read(path, *args, **kwargs)
            size_bytes = bytes_length(result)
            stdout = f"{size_bytes} bytes read" if size_bytes is not None else None
            await self._emit(f"file.read: {path}", started_at, stdout=stdout)
            return result
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            await self._emit(f"file.read: {path}", started_at, stderr=str(exc), exit_code=1)
            raise

    async def remove(self, path: str, *args: object, **kwargs: object) -> object:
        started_at = time.time()
        try:
            result = await self._files.remove(path, *args, **kwargs)
            await self._emit(f"file.delete: {path}", started_at)
            return result
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            await self._emit(f"file.delete: {path}", started_at, stderr=str(exc), exit_code=1)
            raise

    async def delete(self, path: str, *args: object, **kwargs: object) -> object:
        started_at = time.time()
        try:
            result = await self._files.delete(path, *args, **kwargs)
            await self._emit(f"file.delete: {path}", started_at)
            return result
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            await self._emit(f"file.delete: {path}", started_at, stderr=str(exc), exit_code=1)
            raise

    def __getattr__(self, name: str) -> object:
        return getattr(self._files, name)  # slopcop: ignore[no-hasattr-getattr]


class InstrumentedSandbox:
    """Proxy that wraps an AsyncSandbox and emits events via SandboxEventSink.

    Every ``commands.run``, ``files.write``, ``files.read``, and ``run_code``
    call is transparently intercepted, forwarded to the real sandbox, and then
    reported through the sink so that the dashboard can display live activity.
    """

    def __init__(
        self,
        sandbox: AsyncSandbox,
        sink: SandboxEventSink,
        run_id: UUID,
        task_id: UUID,
        max_output_len: int = 4000,
    ):
        self._sandbox = sandbox
        self._sink = sink
        self._run_id = run_id
        self._task_id = task_id
        self._max_output_len = max_output_len

        sid = sandbox.sandbox_id
        self.commands = InstrumentedSandboxCommands(
            sink, run_id, task_id, sid, sandbox.commands, max_output_len
        )
        self.files = InstrumentedSandboxFiles(
            sink, run_id, task_id, sid, sandbox.files, max_output_len
        )

    async def _emit(
        self,
        command: str,
        started_at: float,
        stdout: str | None = None,
        stderr: str | None = None,
        exit_code: int | None = 0,
    ) -> None:
        duration_ms = int((time.time() - started_at) * 1000)
        await self._sink.sandbox_command(
            run_id=self._run_id,
            task_id=self._task_id,
            sandbox_id=self._sandbox.sandbox_id,
            command=_truncate(command, 512) or command,
            stdout=_truncate(coerce_text(stdout), self._max_output_len),
            stderr=_truncate(coerce_text(stderr), self._max_output_len),
            exit_code=exit_code,
            duration_ms=duration_ms,
        )

    async def run_code(self, code: str, *args: object, **kwargs: object) -> object:
        started_at = time.time()
        command = f"python: {preview_python_code(code)}"
        try:
            execution = await self._sandbox.run_code(code, *args, **kwargs)  # ty: ignore[no-matching-overload]
            stdout = None
            stderr = None
            if getattr(execution, "logs", None):  # slopcop: ignore[no-hasattr-getattr]
                stdout = coerce_text(
                    getattr(execution.logs, "stdout", None)  # slopcop: ignore[no-hasattr-getattr]
                )
                stderr = coerce_text(
                    getattr(execution.logs, "stderr", None)  # slopcop: ignore[no-hasattr-getattr]
                )
            error = getattr(execution, "error", None)  # slopcop: ignore[no-hasattr-getattr]
            if error is not None:
                stderr = "\n".join(part for part in [stderr, str(error)] if part)
            await self._emit(
                command,
                started_at,
                stdout=stdout,
                stderr=stderr,
                exit_code=0 if error is None else 1,
            )
            return execution
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            await self._emit(command, started_at, stderr=str(exc), exit_code=1)
            raise

    async def set_timeout(self, *args: object, **kwargs: object) -> object:
        started_at = time.time()
        timeout = kwargs.get("timeout")
        if timeout is None and args:
            timeout = args[0]
        try:
            result = await self._sandbox.set_timeout(*args, **kwargs)
            await self._emit(f"sandbox.timeout: {timeout}s", started_at)
            return result
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            await self._emit(
                f"sandbox.timeout: {timeout}s",
                started_at,
                stderr=str(exc),
                exit_code=1,
            )
            raise

    async def kill(self, *args: object, **kwargs: object) -> object:
        return await self._sandbox.kill(*args, **kwargs)

    @property
    def sandbox_id(self) -> str:
        return self._sandbox.sandbox_id

    def __getattr__(self, name: str) -> object:
        return getattr(self._sandbox, name)  # slopcop: ignore[no-hasattr-getattr]
