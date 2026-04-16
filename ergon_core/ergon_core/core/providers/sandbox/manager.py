"""E2B sandbox lifecycle management for runs."""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Protocol, runtime_checkable
from uuid import UUID

from ergon_core.core.providers.sandbox.event_sink import (
    NoopSandboxEventSink,
    SandboxEventSink,
)
from ergon_core.core.providers.sandbox.utils import _truncate, coerce_text
from ergon_core.core.settings import settings
from pydantic import BaseModel


@runtime_checkable
class UploadableResource(Protocol):
    """Minimal interface for resources passed to ``upload_inputs``."""

    name: str
    file_path: str


try:
    from e2b_code_interpreter import AsyncSandbox  # type: ignore[import-untyped]
except ImportError:
    AsyncSandbox = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


class DownloadedFile(BaseModel):
    """Result of downloading a file from sandbox."""

    sandbox_path: str
    local_path: str
    size_bytes: int


class DownloadedFiles(BaseModel):
    """Result of downloading files from sandbox."""

    files: list[DownloadedFile]


class BaseSandboxManager(ABC):
    """Abstract base class for E2B sandbox management."""

    # Optional name or ID of a pre-built E2B template to provision the sandbox
    # from. When set, it is threaded to ``AsyncSandbox.create(template=...)``,
    # which skips the per-sandbox package install step. Subclasses override
    # this (or set it on the instance in __init__) to point at their benchmark
    # image — e.g. MiniF2FSandboxManager uses "ergon-minif2f-v1".
    template: str | None = None

    _instance: "BaseSandboxManager | None" = None
    _sandboxes: dict[UUID, "AsyncSandbox"] = {}
    _file_registries: dict[UUID, dict[str, str]] = {}
    _created_files_registry: dict[UUID, set[str]] = {}
    _run_ids: dict[UUID, UUID] = {}
    _display_task_ids: dict[UUID, UUID] = {}
    _creation_locks: dict[UUID, asyncio.Lock] = {}
    _event_sink: SandboxEventSink

    def __new__(cls, *args: object, **kwargs: object):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    _event_sink: SandboxEventSink = NoopSandboxEventSink()

    def __init__(self, event_sink: SandboxEventSink | None = None):
        if event_sink is not None:
            self._event_sink = event_sink

    def _get_raw_sandbox(self, task_id: UUID) -> "AsyncSandbox":
        if task_id not in self._sandboxes:
            raise RuntimeError(
                f"Sandbox not created for task_id={task_id}. Call create(task_id) first."
            )
        return self._sandboxes[task_id]

    def _get_display_task_id(self, sandbox_key: UUID) -> UUID:
        return self._display_task_ids.get(sandbox_key, sandbox_key)

    async def _emit_wal_entry(  # slopcop: ignore[max-function-params]
        self,
        sandbox_key: UUID,
        command: str,
        stdout: str | None = None,
        stderr: str | None = None,
        exit_code: int | None = 0,
        started_at: float | None = None,
        duration_ms: int | None = None,
        sandbox_id: str | None = None,
        task_id: UUID | None = None,
    ) -> None:
        raw_sandbox = self._sandboxes.get(sandbox_key)
        resolved_sandbox_id = sandbox_id or (raw_sandbox.sandbox_id if raw_sandbox else None)
        if resolved_sandbox_id is None:
            return

        resolved_duration_ms = duration_ms
        if resolved_duration_ms is None and started_at is not None:
            resolved_duration_ms = int((time.time() - started_at) * 1000)

        max_len = settings.otel_stdout_stderr_max_length
        resolved_run_id = self._run_ids.get(sandbox_key, sandbox_key)
        await self._event_sink.sandbox_command(
            run_id=resolved_run_id,
            task_id=task_id or self._get_display_task_id(sandbox_key),
            sandbox_id=resolved_sandbox_id,
            command=_truncate(command, 512) or command,
            stdout=_truncate(coerce_text(stdout), max_len),
            stderr=_truncate(coerce_text(stderr), max_len),
            exit_code=exit_code,
            duration_ms=resolved_duration_ms,
        )

    def _ensure_registries(self, task_id: UUID) -> None:
        if task_id not in self._file_registries:
            self._file_registries[task_id] = {}
        if task_id not in self._created_files_registry:
            self._created_files_registry[task_id] = set()

    async def _create_directory_structure(self, sandbox: AsyncSandbox, sandbox_key: UUID) -> None:
        create_dirs_code = """
import os
import stat

dirs = [
    '/inputs',
    '/workspace',
    '/workspace/scratchpad',
    '/workspace/final_output',
    '/skills',
    '/tools'
]
created = []
failed = []

for dir_path in dirs:
    try:
        os.makedirs(dir_path, exist_ok=True)
        try:
            os.chmod(dir_path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        except Exception:
            pass
        created.append(dir_path)
    except PermissionError as e:
        failed.append(f"{dir_path}: {e}")

if failed:
    print(f"Failed to create: {', '.join(failed)}")
if created:
    print(f"Created: {', '.join(created)}")
"""
        dir_result = await sandbox.run_code(create_dirs_code, language="python")

        if dir_result.error:
            await self.terminate(sandbox_key)
            raise RuntimeError(f"Failed to create directories: {dir_result.error}")

        try:
            await sandbox.files.write("/inputs/.test_write", b"test")
            await sandbox.files.write("/workspace/scratchpad/.test_write", b"test")
            await sandbox.files.write("/workspace/final_output/.test_write", b"test")
            try:  # slopcop: ignore[no-nested-try]
                await sandbox.commands.run(
                    "rm -f /inputs/.test_write "
                    "/workspace/scratchpad/.test_write "
                    "/workspace/final_output/.test_write"
                )
            except Exception:  # slopcop: ignore[no-broad-except]
                logger.warning(
                    "Failed to clean up test files in sandbox %s",
                    sandbox_key,
                    exc_info=True,
                )
        except Exception as e:  # slopcop: ignore[no-broad-except]
            await self.terminate(sandbox_key)
            raise RuntimeError(
                f"Directories created but not writable. "
                f"Python output: {dir_result.logs.stdout if dir_result.logs else 'N/A'}, Error: {e}"
            )

    async def _upload_directory(
        self,
        sandbox: AsyncSandbox,
        local_dir: Path,
        remote_dir: str,
    ) -> None:
        await sandbox.commands.run(f"mkdir -p {remote_dir}")
        for py_file in local_dir.rglob("*.py"):
            relative_path = py_file.relative_to(local_dir)
            remote_path = f"{remote_dir}/{relative_path}"
            remote_parent = str(Path(remote_path).parent)
            await sandbox.commands.run(f"mkdir -p {remote_parent}")
            content = py_file.read_bytes()
            await sandbox.files.write(remote_path, content)

    @abstractmethod
    async def _install_dependencies(self, sandbox: AsyncSandbox, task_id: UUID) -> None: ...

    async def _verify_setup(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        pass

    async def create(
        self,
        sandbox_key: UUID,
        run_id: UUID,
        timeout_minutes: int = 30,
        envs: dict[str, str] | None = None,
        display_task_id: UUID | None = None,
    ) -> str:
        """Create a new E2B sandbox, set up directories, install deps."""
        if AsyncSandbox is None:
            raise RuntimeError(
                "e2b_code_interpreter is not installed. "
                "Install it with: pip install e2b-code-interpreter"
            )

        display_task_id = display_task_id or sandbox_key
        lock = self._creation_locks.setdefault(sandbox_key, asyncio.Lock())
        async with lock:
            if sandbox_key in self._sandboxes:
                return self._sandboxes[sandbox_key].sandbox_id

            if not settings.e2b_api_key:
                raise ValueError(
                    "E2B_API_KEY is not set. "
                    "Please set E2B_API_KEY in your .env file or environment variables."
                )

            try:
                timeout_seconds = timeout_minutes * 60
                create_kwargs: dict[str, str | int] = {
                    "api_key": settings.e2b_api_key,
                    "timeout": timeout_seconds,
                }
                if envs:
                    create_kwargs["envs"] = envs
                if self.template:
                    create_kwargs["template"] = self.template
                sandbox = await AsyncSandbox.create(**create_kwargs)
            except Exception as e:  # slopcop: ignore[no-broad-except]
                raise RuntimeError(
                    f"Failed to create sandbox for sandbox_key={sandbox_key}: {e}"
                ) from e

            if not sandbox:
                raise RuntimeError("Sandbox object is None after creation")

            self._sandboxes[sandbox_key] = sandbox
            self._ensure_registries(sandbox_key)
            self._run_ids[sandbox_key] = run_id
            self._display_task_ids[sandbox_key] = display_task_id

            await self._event_sink.sandbox_created(
                run_id=run_id,
                task_id=display_task_id,
                sandbox_id=sandbox.sandbox_id,
                timeout_minutes=timeout_minutes,
            )
            await self._emit_wal_entry(
                sandbox_key,
                command="sandbox.created",
                stdout=f"sandbox_id={sandbox.sandbox_id}\ntimeout={timeout_minutes}m",
                exit_code=0,
                duration_ms=0,
            )

            await self._create_directory_structure(sandbox, sandbox_key)
            await self._install_dependencies(sandbox, display_task_id)
            await self._verify_setup(sandbox, display_task_id)

            return sandbox.sandbox_id

    async def upload_inputs(self, task_id: UUID, resources: list[UploadableResource]) -> None:
        """Upload input resources to /inputs/ in the sandbox.

        Each resource must satisfy :class:`UploadableResource` (has ``name``
        and ``file_path``).
        """
        sandbox = self._get_raw_sandbox(task_id)
        self._ensure_registries(task_id)

        for resource in resources:
            sandbox_path = f"/inputs/{resource.name}"
            if not resource.file_path:
                logger.warning("Skipping resource %s: no file_path", resource.name)
                continue
            content = Path(resource.file_path).read_bytes()
            await sandbox.files.write(sandbox_path, content)
            self._file_registries[task_id][resource.file_path] = sandbox_path

    async def upload_file(self, task_id: UUID, local_path: str, sandbox_path: str) -> None:
        sandbox = self._get_raw_sandbox(task_id)
        self._ensure_registries(task_id)
        content = Path(local_path).read_bytes()
        await sandbox.files.write(sandbox_path, content)
        self._file_registries[task_id][local_path] = sandbox_path

    async def download_file(self, task_id: UUID, sandbox_path: str) -> bytes:
        sandbox = self._get_raw_sandbox(task_id)
        try:
            content = await sandbox.files.read(sandbox_path)
            if isinstance(content, str):
                content = content.encode("utf-8")
            return content
        except Exception as e:  # slopcop: ignore[no-broad-except]
            error_msg = str(e).lower()
            if "timeout" in error_msg or "sandbox was not found" in error_msg:
                logger.warning(
                    "Sandbox timeout/not found downloading %s for task_id=%s: %s",
                    sandbox_path,
                    task_id,
                    e,
                )
                raise RuntimeError(
                    f"Sandbox timed out or was not found when downloading {sandbox_path}. "
                    f"Original error: {e}"
                ) from e
            raise

    async def list_files(self, task_id: UUID, sandbox_dir: str = "/workspace") -> list[str]:
        sandbox = self._get_raw_sandbox(task_id)
        try:
            result = await sandbox.commands.run(f"find {sandbox_dir} -type f 2>/dev/null || true")
            if result.exit_code != 0:
                return []
            return [line.strip() for line in result.stdout.split("\n") if line.strip()]
        except Exception as e:  # slopcop: ignore[no-broad-except]
            error_msg = str(e).lower()
            if "timeout" in error_msg or "sandbox was not found" in error_msg:
                logger.warning(
                    "Sandbox timeout/not found listing files for task_id=%s: %s",
                    task_id,
                    e,
                )
                return []
            raise

    async def download_all_outputs(self, task_id: UUID, output_dir: Path) -> DownloadedFiles:
        """Download all files from /workspace/final_output to a local directory."""
        try:
            files = await self.list_files(task_id, "/workspace/final_output")
            downloaded: list[DownloadedFile] = []

            for file_path in files:
                try:  # slopcop: ignore[no-nested-try]
                    content = await self.download_file(task_id, file_path)
                    local_path = output_dir / Path(file_path).name
                    local_path.write_bytes(content)
                    downloaded.append(
                        DownloadedFile(
                            sandbox_path=file_path,
                            local_path=str(local_path),
                            size_bytes=len(content),
                        )
                    )
                except RuntimeError as e:
                    logger.warning("Failed to download %s: %s", file_path, e)
                    continue

            return DownloadedFiles(files=downloaded)

        except Exception as e:  # slopcop: ignore[no-broad-except]
            logger.error(
                "Error downloading outputs for task_id=%s: %s",
                task_id,
                e,
            )
            return DownloadedFiles(files=[])

    def get_sandbox(self, task_id: UUID) -> "AsyncSandbox | None":
        """Return the raw AsyncSandbox for the given task_id, or None."""
        return self._sandboxes.get(task_id)

    def get_sandbox_path(self, task_id: UUID, local_path: str) -> str | None:
        if task_id not in self._file_registries:
            return None
        return self._file_registries[task_id].get(local_path)

    def register_created_file(self, task_id: UUID, sandbox_path: str) -> None:
        self._ensure_registries(task_id)
        self._created_files_registry[task_id].add(sandbox_path)

    async def reset_timeout(self, task_id: UUID, timeout_minutes: int = 30) -> bool:
        sandbox = self._sandboxes.get(task_id)
        if sandbox is None:
            logger.warning("Cannot reset timeout: sandbox not found for task_id=%s", task_id)
            return False
        try:
            timeout_seconds = timeout_minutes * 60
            await sandbox.set_timeout(timeout=timeout_seconds)
            logger.info(
                "Reset sandbox timeout to %d minutes for task_id=%s",
                timeout_minutes,
                task_id,
            )
            return True
        except Exception as e:  # slopcop: ignore[no-broad-except]
            logger.warning("Failed to reset sandbox timeout for task_id=%s: %s", task_id, e)
            return False

    async def terminate(self, task_id: UUID, reason: str = "completed") -> None:
        """Terminate sandbox by task_id key and clean up all registries."""
        sandbox = self._sandboxes.pop(task_id, None)
        if sandbox is None:
            logger.warning(
                "Sandbox not found for task_id=%s. Already terminated or never created.",
                task_id,
            )
            self._file_registries.pop(task_id, None)
            self._created_files_registry.pop(task_id, None)
            self._run_ids.pop(task_id, None)
            self._display_task_ids.pop(task_id, None)
            return

        sandbox_id = sandbox.sandbox_id
        display_task_id = self._get_display_task_id(task_id)
        try:
            await sandbox.kill()
        except Exception as e:  # slopcop: ignore[no-broad-except]
            logger.warning("Error killing sandbox for task_id=%s: %s", task_id, e)
            reason = "error"
        finally:
            self._file_registries.pop(task_id, None)
            self._created_files_registry.pop(task_id, None)
            self._run_ids.pop(task_id, None)
            self._display_task_ids.pop(task_id, None)

            await self._event_sink.sandbox_closed(
                task_id=display_task_id,
                sandbox_id=sandbox_id,
                reason=reason,
            )
            await self._emit_wal_entry(
                task_id,
                command=f"sandbox.closed: {reason}",
                stdout=f"sandbox_id={sandbox_id}",
                exit_code=0,
                duration_ms=0,
                sandbox_id=sandbox_id,
                task_id=display_task_id,
            )

    @staticmethod
    async def terminate_by_sandbox_id(sandbox_id: str) -> bool:
        """Terminate a sandbox directly by its E2B sandbox_id."""
        if AsyncSandbox is None:
            logger.warning(
                "e2b_code_interpreter not installed; cannot terminate sandbox %s",
                sandbox_id,
            )
            return False
        try:
            await AsyncSandbox.kill(sandbox_id=sandbox_id, api_key=settings.e2b_api_key)
            logger.info("Successfully terminated sandbox %s", sandbox_id)
            return True
        except Exception as e:  # slopcop: ignore[no-broad-except]
            error_str = str(e).lower()
            if "not found" in error_str or "404" in error_str:
                logger.info("Sandbox %s already terminated or not found", sandbox_id)
                return False
            logger.warning("Error terminating sandbox %s: %s", sandbox_id, e)
            return False


class DefaultSandboxManager(BaseSandboxManager):
    """No custom dependencies. Used by benchmarks without specific sandbox setup.

    If E2B_API_KEY is not configured (e.g. CI stub runs) the sandbox step is
    skipped entirely and SANDBOX_SKIPPED is returned so the task can still run
    with a worker that doesn't need filesystem access.
    """

    async def create(
        self,
        sandbox_key: UUID,
        run_id: UUID,
        timeout_minutes: int = 30,
        envs: dict[str, str] | None = None,
        display_task_id: UUID | None = None,
    ) -> str:
        if not settings.e2b_api_key:
            # Deferred: avoid a circular import between providers and runtime events.
            from ergon_core.core.runtime.events.task_events import SANDBOX_SKIPPED

            logger.info(
                "E2B_API_KEY not set — skipping sandbox creation for task %s (stub mode)",
                sandbox_key,
            )
            return SANDBOX_SKIPPED
        return await super().create(
            sandbox_key,
            run_id=run_id,
            timeout_minutes=timeout_minutes,
            envs=envs,
            display_task_id=display_task_id,
        )

    async def _install_dependencies(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        pass
