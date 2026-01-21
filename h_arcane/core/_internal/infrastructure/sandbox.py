"""E2B sandbox lifecycle management for runs with skills support."""

import json
from abc import ABC, abstractmethod
from logging import getLogger
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID

from e2b_code_interpreter.code_interpreter_async import AsyncSandbox
from pydantic import BaseModel

from h_arcane.core._internal.db.models import ResourceRecord
from h_arcane.core.settings import settings
from h_arcane.dashboard import dashboard_emitter

logger = getLogger(__name__)

# Generic type for skill responses (all inherit from BaseModel)
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
    """Abstract base class for E2B sandbox management.

    Each benchmark implements its own subclass with benchmark-specific
    dependency installation and setup verification.

    Sandboxes are keyed by task_id (not run_id) to provide isolation per task.
    Multiple workers on the same task share a sandbox, while different tasks
    get their own isolated environments.
    """

    _instance: "BaseSandboxManager | None" = None
    _sandboxes: dict[UUID, AsyncSandbox] = {}  # task_id -> sandbox
    _file_registries: dict[UUID, dict[str, str]] = {}  # task_id -> {local_path: sandbox_path}
    _created_files_registry: dict[UUID, set[str]] = {}  # task_id -> {sandbox_paths}
    _skills_packages: dict[UUID, str] = {}  # task_id -> package name in VM

    def __new__(cls):
        """Singleton pattern - always return the same instance per subclass."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _get_sandbox(self, task_id: UUID) -> AsyncSandbox:
        """Get sandbox for task_id, raising error if not found."""
        if task_id not in self._sandboxes:
            raise RuntimeError(
                f"Sandbox not created for task_id={task_id}. Call create(task_id) first."
            )
        return self._sandboxes[task_id]

    def _ensure_registries(self, task_id: UUID) -> None:
        """Ensure registries exist for task_id."""
        if task_id not in self._file_registries:
            self._file_registries[task_id] = {}
        if task_id not in self._created_files_registry:
            self._created_files_registry[task_id] = set()

    async def _upload_directory(
        self, sandbox: AsyncSandbox, local_dir: Path, remote_dir: str
    ) -> None:
        """
        Upload a directory to the sandbox, preserving structure.

        IMPORTANT: Must include __init__.py files for Python package imports to work!

        Args:
            sandbox: E2B sandbox instance
            local_dir: Local directory to upload
            remote_dir: Remote path in sandbox (e.g., "/skills/gdpeval")
        """
        # Create remote directory
        await sandbox.commands.run(f"mkdir -p {remote_dir}")

        # Upload all .py files (including __init__.py!)
        for py_file in local_dir.rglob("*.py"):
            relative_path = py_file.relative_to(local_dir)
            remote_path = f"{remote_dir}/{relative_path}"

            # Ensure parent directories exist
            remote_parent = str(Path(remote_path).parent)
            await sandbox.commands.run(f"mkdir -p {remote_parent}")

            # Upload file
            content = py_file.read_bytes()
            await sandbox.files.write(remote_path, content)

    async def _create_directory_structure(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        """Create standard directory structure in sandbox.

        Directory structure:
        - /inputs: Input files uploaded for the task
        - /workspace/scratchpad: Work-in-progress files (not evaluated)
        - /workspace/final_output: Final deliverables (downloaded and evaluated)
        - /skills: Benchmark-specific skill scripts
        - /tools: External tools (e.g., Mathlib for MiniF2F)
        """
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
        # Try to set permissions to be writable by all
        try:
            os.chmod(dir_path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)  # 0o777
        except Exception:
            pass  # chmod might fail, but directory creation succeeded
        created.append(dir_path)
    except PermissionError as e:
        failed.append(f"{dir_path}: {e}")

if failed:
    print(f"Failed to create: {', '.join(failed)}")
if created:
    print(f"Successfully created: {', '.join(created)}")
"""
        dir_result = await sandbox.run_code(create_dirs_code, language="python")

        # Check if directory creation was successful
        if dir_result.error:
            await self.terminate(task_id)
            raise RuntimeError(f"Failed to create directories using Python: {dir_result.error}")

        # Verify directories are writable
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
                pass  # Cleanup failure is not critical
        except Exception as e:
            await self.terminate(task_id)
            raise RuntimeError(
                f"Directories created but not writable. Python output: "
                f"{dir_result.logs.stdout if dir_result.logs else 'N/A'}, Error: {e}"
            )

    @abstractmethod
    async def _install_dependencies(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        """Install benchmark-specific dependencies.

        Override in subclass to install required packages/tools.

        Args:
            sandbox: E2B sandbox instance
            task_id: UUID of the task (for logging)
        """
        ...

    async def _verify_setup(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        """Verify setup is complete. Override in subclass if needed.

        Default implementation does nothing.

        Args:
            sandbox: E2B sandbox instance
            task_id: UUID of the task (for logging)
        """
        pass

    async def create(
        self,
        task_id: UUID,
        skills_dir: Path | None = None,
        timeout_minutes: int = 30,
        envs: dict[str, str] | None = None,
    ) -> str:
        """Create and initialize sandbox for a task (idempotent).

        Args:
            task_id: UUID of the task (sandboxes are keyed by task for isolation)
            skills_dir: Path to skills folder to copy (e.g., Path("h_arcane/skills/gdpeval"))
            timeout_minutes: Sandbox timeout in minutes (default: 30).
                            The sandbox will be terminated after this duration.
            envs: Optional dictionary of environment variables to set in the sandbox.
                  These will be available to all code executed in the sandbox.

        Returns:
            The E2B sandbox_id (needed for cleanup across process boundaries)
        """
        # If sandbox already exists for this task_id, return its ID
        if task_id in self._sandboxes:
            return self._sandboxes[task_id].sandbox_id

        # Validate E2B API key before attempting sandbox creation
        if not settings.e2b_api_key:
            raise ValueError(
                "E2B_API_KEY is not set. All benchmarks require E2B API key for sandbox execution. "
                "Please set E2B_API_KEY in your .env file or environment variables."
            )

        try:
            # Convert minutes to seconds for E2B API
            timeout_seconds = timeout_minutes * 60
            create_kwargs: dict[str, Any] = {
                "api_key": settings.e2b_api_key,
                "timeout": timeout_seconds,
            }
            if envs:
                create_kwargs["envs"] = envs
            sandbox = await AsyncSandbox.create(**create_kwargs)
        except Exception as e:
            raise RuntimeError(f"Failed to create sandbox for task_id={task_id}: {e}") from e

        if not sandbox:
            raise RuntimeError("Sandbox object is None after creation")

        # Store sandbox in registry
        self._sandboxes[task_id] = sandbox
        self._ensure_registries(task_id)

        # Create directory structure
        await self._create_directory_structure(sandbox, task_id)

        # Install benchmark-specific dependencies
        await self._install_dependencies(sandbox, task_id)

        # Verify setup
        await self._verify_setup(sandbox, task_id)

        # Upload skills directory if provided
        if skills_dir is not None:
            package_name = skills_dir.name  # e.g., "gdpeval" or "minif2f"
            await self._upload_directory(sandbox, skills_dir, f"/skills/{package_name}")
            self._skills_packages[task_id] = package_name
            logger.info(
                f"Uploaded skills from {skills_dir} to /skills/{package_name} (task_id={task_id})"
            )

        # Emit dashboard sandbox created event
        await dashboard_emitter.sandbox_created(
            task_id=task_id,
            sandbox_id=sandbox.sandbox_id,
            timeout_minutes=timeout_minutes,
        )

        return sandbox.sandbox_id

    async def run_skill(
        self,
        task_id: UUID,
        skill_name: str,
        return_type: type[T],
        **kwargs,
    ) -> T:
        """
        Run a skill in the sandbox with typed response.

        Args:
            task_id: Which sandbox (keyed by task_id)
            skill_name: Name of skill (matches filename without .py)
            return_type: Pydantic model type to parse the result into
            **kwargs: Arguments to skill's main()

        Returns:
            Parsed result of type T

        Example:
            result = await manager.run_skill(
                task_id,
                "read_pdf",
                ReadPDFResponse,
                file_path="/inputs/doc.pdf"
            )
            # result is ReadPDFResponse, not dict
            if result.success:
                print(result.text)
        """
        sandbox = self._get_sandbox(task_id)

        if task_id not in self._skills_packages:
            raise RuntimeError(
                f"No skills package registered for task_id={task_id}. "
                f"Make sure to call create() with skills_dir parameter."
            )

        package = self._skills_packages[task_id]

        # Write kwargs to a temp file to avoid escaping issues
        kwargs_path = f"/tmp/kwargs_{skill_name}.json"
        await sandbox.files.write(kwargs_path, json.dumps(kwargs, default=str).encode())

        # Runner script:
        # - Reads kwargs from file
        # - Calls skill (returns Pydantic model)
        # - Serializes result via .model_dump()
        # - Writes to result file
        result_path = "/tmp/skill_result.json"
        code = f'''
import json
import sys
sys.path.insert(0, '/skills')

from {package}.{skill_name} import main

with open("{kwargs_path}") as f:
    kwargs = json.load(f)

# Run the async main function
# E2B runs code in a Jupyter kernel which supports top-level await
result = await main(**kwargs)

# Skill returns a Pydantic model - use .model_dump() for serialization
with open("{result_path}", "w") as f:
    json.dump(result.model_dump(), f, default=str)

print("SKILL_SUCCESS")
'''

        execution = await sandbox.run_code(code, language="python")

        if execution.error:
            # Return error as the typed response
            error_str = str(execution.error)
            return return_type(success=False, error=error_str)

        # Read result from file and validate into typed response
        try:
            result_data = await sandbox.files.read(result_path)
            # Handle both bytes and str return types from E2B SDK
            if isinstance(result_data, bytes):
                result_str = result_data.decode()
            else:
                result_str = result_data
            raw_result = json.loads(result_str)
            # Pydantic validation
            return return_type.model_validate(raw_result)
        except Exception as e:
            stdout = ""
            if execution.logs and execution.logs.stdout:
                stdout = "".join(execution.logs.stdout)
            return return_type(
                success=False, error=f"Failed to read skill result: {e}. Stdout: {stdout[:200]}"
            )

    async def upload_inputs(self, task_id: UUID, resources: list[ResourceRecord]) -> None:
        """Upload input resources to /inputs/ for a task."""
        sandbox = self._get_sandbox(task_id)
        self._ensure_registries(task_id)

        for resource in resources:
            sandbox_path = f"/inputs/{resource.name}"
            content = resource.load_content()
            await sandbox.files.write(sandbox_path, content)
            self._file_registries[task_id][resource.file_path] = sandbox_path

    async def upload_file(self, task_id: UUID, local_path: str, sandbox_path: str) -> None:
        """Upload a single file to sandbox for a task."""
        sandbox = self._get_sandbox(task_id)
        self._ensure_registries(task_id)

        content = Path(local_path).read_bytes()
        await sandbox.files.write(sandbox_path, content)
        self._file_registries[task_id][local_path] = sandbox_path

    async def download_file(self, task_id: UUID, sandbox_path: str) -> bytes:
        """Download a file from sandbox for a task."""
        sandbox = self._get_sandbox(task_id)

        try:
            content = await sandbox.files.read(sandbox_path)
            # Ensure we return bytes
            if isinstance(content, str):
                return content.encode("utf-8")
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
            raise

    async def list_files(self, task_id: UUID, sandbox_dir: str = "/workspace") -> list[str]:
        """List files in sandbox directory recursively for a task."""
        sandbox = self._get_sandbox(task_id)

        try:
            # Use find command to list files recursively
            result = await sandbox.commands.run(f"find {sandbox_dir} -type f 2>/dev/null || true")
            if result.exit_code != 0:
                return []
            # Parse output - each line is a file path
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
        """Download all files from /workspace/final_output to output_dir for a task.

        Only downloads files from /workspace/final_output - this is where agents
        should place their final deliverables. Files in /workspace/scratchpad are
        work-in-progress and not downloaded.

        Handles sandbox errors gracefully - if sandbox timed out or has connection issues,
        returns empty list and logs a warning. This prevents unnecessary retries at the
        Inngest step level.
        """
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
                    # RuntimeError from download_file (timeout case)
                    # Continue trying other files
                    logger.warning(f"Failed to download {file_path}: {e}")
                    continue

            return DownloadedFiles(files=downloaded)

        except Exception as e:
            # Handle all exceptions gracefully - don't re-raise to avoid unnecessary
            # Inngest step retries. Return empty files list instead.
            logger.error(
                f"Error downloading outputs for task_id={task_id}: {e}. "
                f"No outputs downloaded. This may be due to sandbox timeout or connection issues."
            )
            return DownloadedFiles(files=[])

    def register_created_file(self, task_id: UUID, sandbox_path: str) -> None:
        """Register a file created by a tool for a task."""
        self._ensure_registries(task_id)
        self._created_files_registry[task_id].add(sandbox_path)

    def get_sandbox_path(self, task_id: UUID, local_path: str) -> str | None:
        """Get sandbox path for a local path if it exists in registry for a task."""
        if task_id not in self._file_registries:
            return None
        return self._file_registries[task_id].get(local_path)

    def get_sandbox(self, task_id: UUID) -> AsyncSandbox | None:
        """Get sandbox instance for a task (returns None if not created)."""
        return self._sandboxes.get(task_id)

    async def reset_timeout(self, task_id: UUID, timeout_minutes: int = 30) -> bool:
        """Reset sandbox timeout to prevent expiration during long-running operations.

        This is useful before starting evaluation to ensure the sandbox doesn't
        time out mid-evaluation. The timeout is reset from the current time.

        Args:
            task_id: UUID of the task
            timeout_minutes: New timeout in minutes (default: 30)

        Returns:
            True if timeout was reset, False if sandbox not found
        """
        sandbox = self._sandboxes.get(task_id)
        if sandbox is None:
            logger.warning(f"Cannot reset timeout: sandbox not found for task_id={task_id}")
            return False

        try:
            timeout_seconds: int = timeout_minutes * 60
            await sandbox.set_timeout(timeout=timeout_seconds)  # type: ignore[call-overload]
            logger.info(f"Reset sandbox timeout to {timeout_minutes} minutes for task_id={task_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to reset sandbox timeout for task_id={task_id}: {e}")
            return False

    async def terminate(self, task_id: UUID, reason: str = "completed") -> None:
        """Terminate sandbox for a task (idempotent). Always clears registry even if kill() fails.

        Args:
            task_id: UUID of the task whose sandbox to terminate
            reason: Why the sandbox is being terminated ("completed", "timeout", "error", "cleanup")
        """
        # Use pop() to safely remove - returns None if not present
        sandbox = self._sandboxes.pop(task_id, None)
        if sandbox is None:
            logger.warning(
                f"Sandbox not found for task_id={task_id}. Already terminated or never created."
            )
            # Already terminated or never created - just clean up registries
            self._file_registries.pop(task_id, None)
            self._created_files_registry.pop(task_id, None)
            self._skills_packages.pop(task_id, None)
            return

        sandbox_id = sandbox.sandbox_id
        try:
            await sandbox.kill()  # type: ignore[call-overload]
        except Exception as e:
            # Log but continue - we want to clear the reference even if kill fails
            print(f"Warning: Error killing sandbox for task_id={task_id}: {e}")
            reason = "error"  # Update reason if kill failed
        finally:
            # Always clear registries to prevent reuse
            self._file_registries.pop(task_id, None)
            self._created_files_registry.pop(task_id, None)
            self._skills_packages.pop(task_id, None)

            # Emit dashboard sandbox closed event
            await dashboard_emitter.sandbox_closed(
                task_id=task_id,
                sandbox_id=sandbox_id,
                reason=reason,
            )

    @staticmethod
    async def terminate_by_sandbox_id(sandbox_id: str) -> bool:
        """Terminate a sandbox by its E2B sandbox_id.

        This is used for cleanup across process boundaries where we don't have
        the sandbox object in memory, but we have the sandbox_id stored in the database.

        Args:
            sandbox_id: The E2B sandbox ID (stored in Run.e2b_sandbox_id)

        Returns:
            True if sandbox was killed, False if it was already terminated or not found
        """
        try:
            # Use the class method variant to kill by sandbox_id directly
            # This avoids needing to connect first
            await AsyncSandbox.kill(sandbox_id=sandbox_id, api_key=settings.e2b_api_key)
            logger.info(f"Successfully terminated sandbox {sandbox_id}")
            return True
        except Exception as e:
            error_str = str(e).lower()
            # Sandbox already terminated or doesn't exist - this is fine
            if "not found" in error_str or "404" in error_str:
                logger.info(f"Sandbox {sandbox_id} already terminated or not found")
                return False
            # Log unexpected errors but don't fail
            logger.warning(f"Error terminating sandbox {sandbox_id}: {e}")
            return False
