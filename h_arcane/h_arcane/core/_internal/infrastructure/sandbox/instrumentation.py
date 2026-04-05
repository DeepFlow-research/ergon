"""Instrumented sandbox proxies that emit WAL events."""

import time
from typing import TYPE_CHECKING, Any
from uuid import UUID

from e2b.sandbox.commands.command_handle import CommandExitException  # type: ignore[import-untyped]
from e2b_code_interpreter.code_interpreter_async import AsyncSandbox  # type: ignore[import-untyped]

from h_arcane.core._internal.infrastructure.sandbox.utils import (
    bytes_length,
    coerce_text,
    preview_python_code,
)

if TYPE_CHECKING:
    from h_arcane.core._internal.infrastructure.sandbox.manager import BaseSandboxManager


class InstrumentedSandboxCommands:
    """Proxy around sandbox shell commands that emits WAL events."""

    def __init__(self, manager: "BaseSandboxManager", sandbox_key: UUID, commands: Any):
        self._manager = manager
        self._sandbox_key = sandbox_key
        self._commands = commands

    async def run(self, command: str, *args: Any, **kwargs: Any) -> Any:
        started_at = time.time()
        try:
            result = await self._commands.run(command, *args, **kwargs)
            await self._manager._emit_wal_entry(
                self._sandbox_key,
                command=command,
                stdout=coerce_text(getattr(result, "stdout", None)),
                stderr=coerce_text(getattr(result, "stderr", None)),
                exit_code=getattr(result, "exit_code", 0),
                started_at=started_at,
            )
            return result
        except CommandExitException as exc:
            await self._manager._emit_wal_entry(
                self._sandbox_key,
                command=command,
                stdout=coerce_text(exc.stdout),
                stderr=coerce_text(exc.stderr),
                exit_code=exc.exit_code,
                started_at=started_at,
            )
            raise
        except Exception as exc:
            await self._manager._emit_wal_entry(
                self._sandbox_key,
                command=command,
                stderr=str(exc),
                exit_code=1,
                started_at=started_at,
            )
            raise

    def __getattr__(self, name: str) -> Any:
        return getattr(self._commands, name)


class InstrumentedSandboxFiles:
    """Proxy around sandbox file operations that emits WAL events."""

    def __init__(self, manager: "BaseSandboxManager", sandbox_key: UUID, files: Any):
        self._manager = manager
        self._sandbox_key = sandbox_key
        self._files = files

    async def write(self, path: str, content: Any, *args: Any, **kwargs: Any) -> Any:
        started_at = time.time()
        size_bytes = bytes_length(content)
        try:
            result = await self._files.write(path, content, *args, **kwargs)
            stdout = f"{size_bytes} bytes written" if size_bytes is not None else None
            await self._manager._emit_wal_entry(
                self._sandbox_key,
                command=f"file.write: {path}",
                stdout=stdout,
                exit_code=0,
                started_at=started_at,
            )
            return result
        except Exception as exc:
            await self._manager._emit_wal_entry(
                self._sandbox_key,
                command=f"file.write: {path}",
                stderr=str(exc),
                exit_code=1,
                started_at=started_at,
            )
            raise

    async def read(self, path: str, *args: Any, **kwargs: Any) -> Any:
        started_at = time.time()
        try:
            result = await self._files.read(path, *args, **kwargs)
            size_bytes = bytes_length(result)
            stdout = f"{size_bytes} bytes read" if size_bytes is not None else None
            await self._manager._emit_wal_entry(
                self._sandbox_key,
                command=f"file.read: {path}",
                stdout=stdout,
                exit_code=0,
                started_at=started_at,
            )
            return result
        except Exception as exc:
            await self._manager._emit_wal_entry(
                self._sandbox_key,
                command=f"file.read: {path}",
                stderr=str(exc),
                exit_code=1,
                started_at=started_at,
            )
            raise

    async def remove(self, path: str, *args: Any, **kwargs: Any) -> Any:
        started_at = time.time()
        try:
            result = await self._files.remove(path, *args, **kwargs)
            await self._manager._emit_wal_entry(
                self._sandbox_key,
                command=f"file.delete: {path}",
                exit_code=0,
                started_at=started_at,
            )
            return result
        except Exception as exc:
            await self._manager._emit_wal_entry(
                self._sandbox_key,
                command=f"file.delete: {path}",
                stderr=str(exc),
                exit_code=1,
                started_at=started_at,
            )
            raise

    async def delete(self, path: str, *args: Any, **kwargs: Any) -> Any:
        started_at = time.time()
        try:
            result = await self._files.delete(path, *args, **kwargs)
            await self._manager._emit_wal_entry(
                self._sandbox_key,
                command=f"file.delete: {path}",
                exit_code=0,
                started_at=started_at,
            )
            return result
        except Exception as exc:
            await self._manager._emit_wal_entry(
                self._sandbox_key,
                command=f"file.delete: {path}",
                stderr=str(exc),
                exit_code=1,
                started_at=started_at,
            )
            raise

    def __getattr__(self, name: str) -> Any:
        return getattr(self._files, name)


class InstrumentedSandbox:
    """Proxy that turns sandbox activity into dashboard WAL events."""

    def __init__(self, manager: "BaseSandboxManager", sandbox_key: UUID, sandbox: AsyncSandbox):
        self._manager = manager
        self._sandbox_key = sandbox_key
        self._sandbox = sandbox
        self.commands = InstrumentedSandboxCommands(manager, sandbox_key, sandbox.commands)
        self.files = InstrumentedSandboxFiles(manager, sandbox_key, sandbox.files)

    async def run_code(self, code: str, *args: Any, **kwargs: Any) -> Any:
        started_at = time.time()
        command = f"python: {preview_python_code(code)}"
        try:
            execution = await self._sandbox.run_code(code, *args, **kwargs)
            stdout = None
            stderr = None
            if getattr(execution, "logs", None):
                stdout = coerce_text(getattr(execution.logs, "stdout", None))
                stderr = coerce_text(getattr(execution.logs, "stderr", None))
            error = getattr(execution, "error", None)
            if error is not None:
                stderr = "\n".join(part for part in [stderr, str(error)] if part)
            await self._manager._emit_wal_entry(
                self._sandbox_key,
                command=command,
                stdout=stdout,
                stderr=stderr,
                exit_code=0 if error is None else 1,
                started_at=started_at,
            )
            return execution
        except Exception as exc:
            await self._manager._emit_wal_entry(
                self._sandbox_key,
                command=command,
                stderr=str(exc),
                exit_code=1,
                started_at=started_at,
            )
            raise

    async def set_timeout(self, *args: Any, **kwargs: Any) -> Any:
        started_at = time.time()
        timeout = kwargs.get("timeout")
        if timeout is None and args:
            timeout = args[0]
        try:
            result = await self._sandbox.set_timeout(*args, **kwargs)
            await self._manager._emit_wal_entry(
                self._sandbox_key,
                command=f"sandbox.timeout: {timeout}s",
                exit_code=0,
                started_at=started_at,
            )
            return result
        except Exception as exc:
            await self._manager._emit_wal_entry(
                self._sandbox_key,
                command=f"sandbox.timeout: {timeout}s",
                stderr=str(exc),
                exit_code=1,
                started_at=started_at,
            )
            raise

    async def kill(self, *args: Any, **kwargs: Any) -> Any:
        return await self._sandbox.kill(*args, **kwargs)

    @property
    def sandbox_id(self) -> str:
        return self._sandbox.sandbox_id

    def __getattr__(self, name: str) -> Any:
        return getattr(self._sandbox, name)
