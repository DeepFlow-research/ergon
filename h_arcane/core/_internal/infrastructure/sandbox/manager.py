"""E2B sandbox lifecycle management for runs with skills support."""

import asyncio
import json
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from logging import getLogger
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID

from e2b_code_interpreter.code_interpreter_async import AsyncSandbox  # type: ignore[import-untyped]
from pydantic import BaseModel

from h_arcane.core._internal.db.models import ResourceRecord
from h_arcane.core._internal.infrastructure.sandbox.events import (
    NoopSandboxEventSink,
    SandboxEventSink,
)
from h_arcane.core._internal.infrastructure.sandbox.instrumentation import InstrumentedSandbox
from h_arcane.core._internal.infrastructure.sandbox.utils import coerce_text
from h_arcane.core._internal.infrastructure.tracing import (
    CompletedSpan,
    get_trace_sink,
    sandbox_file_op_context,
    truncate_text,
)
from h_arcane.core._internal.utils import utcnow
from h_arcane.core.settings import settings

logger = getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


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

    _instance: "BaseSandboxManager | None" = None
    _sandboxes: dict[UUID, AsyncSandbox] = {}
    _file_registries: dict[UUID, dict[str, str]] = {}
    _created_files_registry: dict[UUID, set[str]] = {}
    _skills_packages: dict[UUID, str] = {}
    _run_ids: dict[UUID, UUID] = {}
    _display_task_ids: dict[UUID, UUID] = {}
    _creation_locks: dict[UUID, asyncio.Lock] = {}
    _event_sink: SandboxEventSink

    def __new__(cls, *args: Any, **kwargs: Any):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, event_sink: SandboxEventSink | None = None):
        if event_sink is not None:
            self._event_sink = event_sink
        elif not hasattr(self, "_event_sink"):
            self._event_sink = NoopSandboxEventSink()

    def _get_raw_sandbox(self, task_id: UUID) -> AsyncSandbox:
        if task_id not in self._sandboxes:
            raise RuntimeError(
                f"Sandbox not created for task_id={task_id}. Call create(task_id) first."
            )
        return self._sandboxes[task_id]

    def _get_display_task_id(self, sandbox_key: UUID) -> UUID:
        return self._display_task_ids.get(sandbox_key, sandbox_key)

    async def _emit_wal_entry(
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

        await self._event_sink.sandbox_command(
            task_id=task_id or self._get_display_task_id(sandbox_key),
            sandbox_id=resolved_sandbox_id,
            command=truncate_text(command, 512),
            stdout=truncate_text(coerce_text(stdout), settings.otel_stdout_stderr_max_length),
            stderr=truncate_text(coerce_text(stderr), settings.otel_stdout_stderr_max_length),
            exit_code=exit_code,
            duration_ms=resolved_duration_ms,
        )

    def _get_sandbox(self, task_id: UUID) -> InstrumentedSandbox:
        return InstrumentedSandbox(self, task_id, self._get_raw_sandbox(task_id))

    def _ensure_registries(self, task_id: UUID) -> None:
        if task_id not in self._file_registries:
            self._file_registries[task_id] = {}
        if task_id not in self._created_files_registry:
            self._created_files_registry[task_id] = set()

    def _emit_file_op_span(
        self,
        task_id: UUID,
        operation: str,
        started_at: float,
        attributes: dict[str, Any] | None = None,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        run_id = self._run_ids.get(task_id)
        if run_id is None:
            return
        trace_sink = get_trace_sink()
        trace_sink.emit_span(
            CompletedSpan(
                name="sandbox.file_ops",
                context=sandbox_file_op_context(
                    run_id,
                    task_id,
                    operation,
                    attributes={"operation": operation},
                ),
                start_time=datetime.fromtimestamp(started_at, tz=UTC),
                end_time=utcnow(),
                attributes={**(attributes or {}), "success": success, "error": error},
                status_code="ok" if success else "error",
                status_message=error,
            )
        )

    async def _upload_directory(
        self, sandbox: AsyncSandbox, local_dir: Path, remote_dir: str
    ) -> None:
        await sandbox.commands.run(f"mkdir -p {remote_dir}")

        for py_file in local_dir.rglob("*.py"):
            relative_path = py_file.relative_to(local_dir)
            remote_path = f"{remote_dir}/{relative_path}"
            remote_parent = str(Path(remote_path).parent)
            await sandbox.commands.run(f"mkdir -p {remote_parent}")
            content = py_file.read_bytes()
            await sandbox.files.write(remote_path, content)

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
    print(f"Successfully created: {', '.join(created)}")
"""
        dir_result = await sandbox.run_code(create_dirs_code, language="python")

        if dir_result.error:
            await self.terminate(sandbox_key)
            raise RuntimeError(f"Failed to create directories using Python: {dir_result.error}")

        try:
            await sandbox.files.write("/inputs/.test_write", b"test")
            await sandbox.files.write("/workspace/scratchpad/.test_write", b"test")
            await sandbox.files.write("/workspace/final_output/.test_write", b"test")
            try:
                await sandbox.commands.run(
                    "rm -f /inputs/.test_write "
                    "/workspace/scratchpad/.test_write "
                    "/workspace/final_output/.test_write"
                )
            except Exception:
                pass
        except Exception as e:
            await self.terminate(sandbox_key)
            raise RuntimeError(
                f"Directories created but not writable. Python output: "
                f"{dir_result.logs.stdout if dir_result.logs else 'N/A'}, Error: {e}"
            )

    @abstractmethod
    async def _install_dependencies(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        ...

    async def _verify_setup(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        pass

    async def create(
        self,
        sandbox_key: UUID,
        run_id: UUID,
        skills_dir: Path | None = None,
        timeout_minutes: int = 30,
        envs: dict[str, str] | None = None,
        display_task_id: UUID | None = None,
    ) -> str:
        display_task_id = display_task_id or sandbox_key
        lock = self._creation_locks.setdefault(sandbox_key, asyncio.Lock())
        async with lock:
            if sandbox_key in self._sandboxes:
                return self._sandboxes[sandbox_key].sandbox_id

            if not settings.e2b_api_key:
                raise ValueError(
                    "E2B_API_KEY is not set. All benchmarks require E2B API key for sandbox execution. "
                    "Please set E2B_API_KEY in your .env file or environment variables."
                )

            try:
                timeout_seconds = timeout_minutes * 60
                create_kwargs: dict[str, Any] = {
                    "api_key": settings.e2b_api_key,
                    "timeout": timeout_seconds,
                }
                if envs:
                    create_kwargs["envs"] = envs
                sandbox = await AsyncSandbox.create(**create_kwargs)
            except Exception as e:
                raise RuntimeError(
                    f"Failed to create sandbox for sandbox_key={sandbox_key}: {e}"
                ) from e

            if not sandbox:
                raise RuntimeError("Sandbox object is None after creation")

            self._sandboxes[sandbox_key] = sandbox
            self._ensure_registries(sandbox_key)
            self._run_ids[sandbox_key] = run_id
            self._display_task_ids[sandbox_key] = display_task_id

            instrumented_sandbox = self._get_sandbox(sandbox_key)
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

            await self._create_directory_structure(instrumented_sandbox, sandbox_key)
            await self._install_dependencies(instrumented_sandbox, display_task_id)
            await self._verify_setup(instrumented_sandbox, display_task_id)

            if skills_dir is not None:
                package_name = skills_dir.name
                await self._upload_directory(instrumented_sandbox, skills_dir, f"/skills/{package_name}")
                self._skills_packages[sandbox_key] = package_name
                logger.info(
                    "Uploaded skills from %s to /skills/%s (sandbox_key=%s task_id=%s)",
                    skills_dir,
                    package_name,
                    sandbox_key,
                    display_task_id,
                )

            return sandbox.sandbox_id

    async def run_skill(
        self,
        task_id: UUID,
        skill_name: str,
        return_type: type[T],
        **kwargs,
    ) -> T:
        sandbox = self._get_sandbox(task_id)
        run_id = self._run_ids.get(task_id)
        started_at = time.time()

        if task_id not in self._skills_packages:
            raise RuntimeError(
                f"No skills package registered for task_id={task_id}. "
                f"Make sure to call create() with skills_dir parameter."
            )

        package = self._skills_packages[task_id]
        kwargs_path = f"/tmp/kwargs_{skill_name}.json"
        await sandbox.files.write(kwargs_path, json.dumps(kwargs, default=str).encode())

        result_path = "/tmp/skill_result.json"
        code = f'''
import json
import sys
sys.path.insert(0, '/skills')

from {package}.{skill_name} import main

with open("{kwargs_path}") as f:
    kwargs = json.load(f)

result = await main(**kwargs)

with open("{result_path}", "w") as f:
    json.dump(result.model_dump(), f, default=str)

print("SKILL_SUCCESS")
'''

        execution = await sandbox.run_code(code, language="python")

        if execution.error:
            error_str = str(execution.error)
            if run_id is not None:
                get_trace_sink().emit_span(
                    CompletedSpan(
                        name="sandbox.run_skill",
                        context=sandbox_file_op_context(
                            run_id,
                            task_id,
                            f"run_skill:{skill_name}",
                            attributes={"skill_name": skill_name},
                        ),
                        start_time=datetime.fromtimestamp(started_at, tz=UTC),
                        end_time=utcnow(),
                        attributes={"skill_name": skill_name, "success": False, "error": error_str},
                        status_code="error",
                        status_message=error_str,
                    )
                )
            return return_type(success=False, error=error_str)

        try:
            result_data = await sandbox.files.read(result_path)
            if isinstance(result_data, bytes):
                result_str = result_data.decode()
            else:
                result_str = result_data
            raw_result = json.loads(result_str)
            if run_id is not None:
                stdout = None
                if execution.logs and execution.logs.stdout:
                    stdout = "".join(execution.logs.stdout)
                stderr = None
                if execution.logs and execution.logs.stderr:
                    stderr = "".join(execution.logs.stderr)
                get_trace_sink().emit_span(
                    CompletedSpan(
                        name="sandbox.run_skill",
                        context=sandbox_file_op_context(
                            run_id,
                            task_id,
                            f"run_skill:{skill_name}",
                            attributes={"skill_name": skill_name},
                        ),
                        start_time=datetime.fromtimestamp(started_at, tz=UTC),
                        end_time=utcnow(),
                        attributes={
                            "skill_name": skill_name,
                            "success": True,
                            "stdout": truncate_text(stdout, settings.otel_stdout_stderr_max_length),
                            "stderr": truncate_text(stderr, settings.otel_stdout_stderr_max_length),
                        },
                    )
                )
            return return_type.model_validate(raw_result)
        except Exception as e:
            stdout = ""
            if execution.logs and execution.logs.stdout:
                stdout = "".join(execution.logs.stdout)
            if run_id is not None:
                get_trace_sink().emit_span(
                    CompletedSpan(
                        name="sandbox.run_skill",
                        context=sandbox_file_op_context(
                            run_id,
                            task_id,
                            f"run_skill:{skill_name}",
                            attributes={"skill_name": skill_name},
                        ),
                        start_time=datetime.fromtimestamp(started_at, tz=UTC),
                        end_time=utcnow(),
                        attributes={
                            "skill_name": skill_name,
                            "success": False,
                            "stdout": truncate_text(stdout, settings.otel_stdout_stderr_max_length),
                            "error": str(e),
                        },
                        status_code="error",
                        status_message=str(e),
                    )
                )
            return return_type(
                success=False, error=f"Failed to read skill result: {e}. Stdout: {stdout[:200]}"
            )

    async def upload_inputs(self, task_id: UUID, resources: list[ResourceRecord]) -> None:
        sandbox = self._get_sandbox(task_id)
        self._ensure_registries(task_id)
        started_at = time.time()

        for resource in resources:
            sandbox_path = f"/inputs/{resource.name}"
            content = resource.load_content()
            await sandbox.files.write(sandbox_path, content)
            self._file_registries[task_id][resource.file_path] = sandbox_path
        self._emit_file_op_span(
            task_id,
            "upload_inputs",
            started_at,
            attributes={"file_count": len(resources)},
        )

    async def upload_file(self, task_id: UUID, local_path: str, sandbox_path: str) -> None:
        sandbox = self._get_sandbox(task_id)
        self._ensure_registries(task_id)
        started_at = time.time()

        content = Path(local_path).read_bytes()
        await sandbox.files.write(sandbox_path, content)
        self._file_registries[task_id][local_path] = sandbox_path
        self._emit_file_op_span(
            task_id,
            "upload_file",
            started_at,
            attributes={"local_path": local_path, "sandbox_path": sandbox_path, "size_bytes": len(content)},
        )

    async def download_file(self, task_id: UUID, sandbox_path: str) -> bytes:
        sandbox = self._get_sandbox(task_id)
        started_at = time.time()

        try:
            content = await sandbox.files.read(sandbox_path)
            if isinstance(content, str):
                content = content.encode("utf-8")
            self._emit_file_op_span(
                task_id,
                "download_file",
                started_at,
                attributes={"sandbox_path": sandbox_path, "size_bytes": len(content)},
            )
            return content
        except Exception as e:
            error_msg = str(e).lower()
            if "timeout" in error_msg or "sandbox was not found" in error_msg:
                logger.warning(
                    f"Sandbox timeout/not found when downloading file {sandbox_path} for task_id={task_id}: {e}. "
                    f"Sandbox may have timed out during execution."
                )
                raise RuntimeError(
                    f"Sandbox timed out or was not found when downloading {sandbox_path}. "
                    f"Original error: {e}"
                ) from e
            self._emit_file_op_span(
                task_id,
                "download_file",
                started_at,
                attributes={"sandbox_path": sandbox_path},
                success=False,
                error=str(e),
            )
            raise

    async def list_files(self, task_id: UUID, sandbox_dir: str = "/workspace") -> list[str]:
        sandbox = self._get_sandbox(task_id)

        try:
            result = await sandbox.commands.run(f"find {sandbox_dir} -type f 2>/dev/null || true")
            if result.exit_code != 0:
                return []
            files = [line.strip() for line in result.stdout.split("\n") if line.strip()]
            return files
        except Exception as e:
            error_msg = str(e).lower()
            if "timeout" in error_msg or "sandbox was not found" in error_msg:
                logger.warning(
                    f"Sandbox timeout/not found when listing files for task_id={task_id}: {e}. "
                    f"Sandbox may have timed out during execution."
                )
                return []
            raise

    async def download_all_outputs(self, task_id: UUID, output_dir: Path) -> DownloadedFiles:
        started_at = time.time()
        try:
            files = await self.list_files(task_id, "/workspace/final_output")
            downloaded: list[DownloadedFile] = []

            for file_path in files:
                try:
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
                    logger.warning(f"Failed to download {file_path}: {e}")
                    continue

            self._emit_file_op_span(
                task_id,
                "download_all_outputs",
                started_at,
                attributes={"file_count": len(downloaded), "output_dir": str(output_dir)},
            )
            return DownloadedFiles(files=downloaded)

        except Exception as e:
            logger.error(
                f"Error downloading outputs for task_id={task_id}: {e}. "
                f"No outputs downloaded. This may be due to sandbox timeout or connection issues."
            )
            self._emit_file_op_span(
                task_id,
                "download_all_outputs",
                started_at,
                attributes={"output_dir": str(output_dir)},
                success=False,
                error=str(e),
            )
            return DownloadedFiles(files=[])

    def register_created_file(self, task_id: UUID, sandbox_path: str) -> None:
        self._ensure_registries(task_id)
        self._created_files_registry[task_id].add(sandbox_path)

    def get_sandbox_path(self, task_id: UUID, local_path: str) -> str | None:
        if task_id not in self._file_registries:
            return None
        return self._file_registries[task_id].get(local_path)

    def get_sandbox(self, task_id: UUID) -> InstrumentedSandbox | None:
        sandbox = self._sandboxes.get(task_id)
        if sandbox is None:
            return None
        return InstrumentedSandbox(self, task_id, sandbox)

    async def reset_timeout(self, task_id: UUID, timeout_minutes: int = 30) -> bool:
        sandbox = self._sandboxes.get(task_id)
        if sandbox is None:
            logger.warning(f"Cannot reset timeout: sandbox not found for task_id={task_id}")
            return False

        try:
            timeout_seconds: int = timeout_minutes * 60
            instrumented_sandbox = InstrumentedSandbox(self, task_id, sandbox)
            await instrumented_sandbox.set_timeout(timeout=timeout_seconds)  # type: ignore[call-overload]
            logger.info(f"Reset sandbox timeout to {timeout_minutes} minutes for task_id={task_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to reset sandbox timeout for task_id={task_id}: {e}")
            return False

    async def terminate(self, task_id: UUID, reason: str = "completed") -> None:
        sandbox = self._sandboxes.pop(task_id, None)
        if sandbox is None:
            logger.warning(
                f"Sandbox not found for task_id={task_id}. Already terminated or never created."
            )
            self._file_registries.pop(task_id, None)
            self._created_files_registry.pop(task_id, None)
            self._skills_packages.pop(task_id, None)
            self._run_ids.pop(task_id, None)
            self._display_task_ids.pop(task_id, None)
            return

        sandbox_id = sandbox.sandbox_id
        display_task_id = self._get_display_task_id(task_id)
        try:
            await sandbox.kill()  # type: ignore[call-overload]
        except Exception as e:
            print(f"Warning: Error killing sandbox for task_id={task_id}: {e}")
            reason = "error"
        finally:
            self._file_registries.pop(task_id, None)
            self._created_files_registry.pop(task_id, None)
            self._skills_packages.pop(task_id, None)
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
        try:
            await AsyncSandbox.kill(sandbox_id=sandbox_id, api_key=settings.e2b_api_key)
            logger.info(f"Successfully terminated sandbox {sandbox_id}")
            return True
        except Exception as e:
            error_str = str(e).lower()
            if "not found" in error_str or "404" in error_str:
                logger.info(f"Sandbox {sandbox_id} already terminated or not found")
                return False
            logger.warning(f"Error terminating sandbox {sandbox_id}: {e}")
            return False
