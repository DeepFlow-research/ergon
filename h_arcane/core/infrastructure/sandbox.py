"""E2B sandbox lifecycle management for runs with skills support."""

import json
from abc import ABC, abstractmethod
from logging import getLogger
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID

from e2b_code_interpreter.code_interpreter_async import AsyncSandbox
from pydantic import BaseModel

from h_arcane.core.db.models import Resource
from h_arcane.settings import settings

logger = getLogger(__name__)

# Generic type for skill responses (all inherit from BaseModel)
T = TypeVar("T", bound=BaseModel)


class DownloadedFile(BaseModel):
    """Result of downloading a file from sandbox."""

    sandbox_path: str
    local_path: str
    size_bytes: int


class BaseSandboxManager(ABC):
    """Abstract base class for E2B sandbox management.

    Each benchmark implements its own subclass with benchmark-specific
    dependency installation and setup verification.
    """

    _instance: "BaseSandboxManager | None" = None
    _sandboxes: dict[UUID, AsyncSandbox] = {}  # run_id -> sandbox
    _file_registries: dict[UUID, dict[str, str]] = {}  # run_id -> {local_path: sandbox_path}
    _created_files_registry: dict[UUID, set[str]] = {}  # run_id -> {sandbox_paths}
    _skills_packages: dict[UUID, str] = {}  # run_id -> package name in VM

    def __new__(cls):
        """Singleton pattern - always return the same instance per subclass."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _get_sandbox(self, run_id: UUID) -> AsyncSandbox:
        """Get sandbox for run_id, raising error if not found."""
        if run_id not in self._sandboxes:
            raise RuntimeError(
                f"Sandbox not created for run_id={run_id}. Call create(run_id) first."
            )
        return self._sandboxes[run_id]

    def _ensure_registries(self, run_id: UUID) -> None:
        """Ensure registries exist for run_id."""
        if run_id not in self._file_registries:
            self._file_registries[run_id] = {}
        if run_id not in self._created_files_registry:
            self._created_files_registry[run_id] = set()

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

    async def _create_directory_structure(self, sandbox: AsyncSandbox, run_id: UUID) -> None:
        """Create standard directory structure in sandbox."""
        create_dirs_code = """
import os
import stat

dirs = ['/inputs', '/workspace', '/skills']
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
            await self.terminate(run_id)
            raise RuntimeError(f"Failed to create directories using Python: {dir_result.error}")

        # Verify directories are writable
        try:
            await sandbox.files.write("/inputs/.test_write", b"test")
            await sandbox.files.write("/workspace/.test_write", b"test")
            try:
                await sandbox.commands.run("rm -f /inputs/.test_write /workspace/.test_write")
            except Exception:
                pass  # Cleanup failure is not critical
        except Exception as e:
            await self.terminate(run_id)
            raise RuntimeError(
                f"Directories created but not writable. Python output: "
                f"{dir_result.logs.stdout if dir_result.logs else 'N/A'}, Error: {e}"
            )

    @abstractmethod
    async def _install_dependencies(self, sandbox: AsyncSandbox, run_id: UUID) -> None:
        """Install benchmark-specific dependencies.

        Override in subclass to install required packages/tools.

        Args:
            sandbox: E2B sandbox instance
            run_id: UUID of the run (for logging)
        """
        ...

    async def _verify_setup(self, sandbox: AsyncSandbox, run_id: UUID) -> None:
        """Verify setup is complete. Override in subclass if needed.

        Default implementation does nothing.

        Args:
            sandbox: E2B sandbox instance
            run_id: UUID of the run (for logging)
        """
        pass

    async def create(
        self,
        run_id: UUID,
        skills_dir: Path | None = None,
        timeout_minutes: int = 30,
        envs: dict[str, str] | None = None,
    ) -> None:
        """Create and initialize sandbox for a run (idempotent).

        Args:
            run_id: UUID of the run
            skills_dir: Path to skills folder to copy (e.g., Path("h_arcane/skills/gdpeval"))
            timeout_minutes: Sandbox timeout in minutes (default: 30).
                            The sandbox will be terminated after this duration.
            envs: Optional dictionary of environment variables to set in the sandbox.
                  These will be available to all code executed in the sandbox.
        """
        # If sandbox already exists for this run_id, skip creation
        if run_id in self._sandboxes:
            return

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
            raise RuntimeError(f"Failed to create sandbox for run_id={run_id}: {e}") from e

        if not sandbox:
            raise RuntimeError("Sandbox object is None after creation")

        # Store sandbox in registry
        self._sandboxes[run_id] = sandbox
        self._ensure_registries(run_id)

        # Create directory structure
        await self._create_directory_structure(sandbox, run_id)

        # Install benchmark-specific dependencies
        await self._install_dependencies(sandbox, run_id)

        # Verify setup
        await self._verify_setup(sandbox, run_id)

        # Upload skills directory if provided
        if skills_dir is not None:
            package_name = skills_dir.name  # e.g., "gdpeval" or "minif2f"
            await self._upload_directory(sandbox, skills_dir, f"/skills/{package_name}")
            self._skills_packages[run_id] = package_name
            logger.info(
                f"Uploaded skills from {skills_dir} to /skills/{package_name} (run_id={run_id})"
            )

    async def run_skill(
        self,
        run_id: UUID,
        skill_name: str,
        return_type: type[T],
        **kwargs,
    ) -> T:
        """
        Run a skill in the sandbox with typed response.

        Args:
            run_id: Which sandbox
            skill_name: Name of skill (matches filename without .py)
            return_type: Pydantic model type to parse the result into
            **kwargs: Arguments to skill's main()

        Returns:
            Parsed result of type T

        Example:
            result = await manager.run_skill(
                run_id,
                "read_pdf",
                ReadPDFResponse,
                file_path="/inputs/doc.pdf"
            )
            # result is ReadPDFResponse, not dict
            if result.success:
                print(result.text)
        """
        sandbox = self._get_sandbox(run_id)

        if run_id not in self._skills_packages:
            raise RuntimeError(
                f"No skills package registered for run_id={run_id}. "
                f"Make sure to call create() with skills_dir parameter."
            )

        package = self._skills_packages[run_id]

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
            return return_type(success=False, error=error_str)  # type: ignore[call-arg]

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
            return return_type(  # type: ignore[call-arg]
                success=False, error=f"Failed to read skill result: {e}. Stdout: {stdout[:200]}"
            )

    async def upload_inputs(self, run_id: UUID, resources: list[Resource]) -> None:
        """Upload input resources to /inputs/ for a run."""
        sandbox = self._get_sandbox(run_id)
        self._ensure_registries(run_id)

        for resource in resources:
            sandbox_path = f"/inputs/{resource.name}"
            content = resource.load_content()
            await sandbox.files.write(sandbox_path, content)
            self._file_registries[run_id][resource.file_path] = sandbox_path

    async def upload_file(self, run_id: UUID, local_path: str, sandbox_path: str) -> None:
        """Upload a single file to sandbox for a run."""
        sandbox = self._get_sandbox(run_id)
        self._ensure_registries(run_id)

        content = Path(local_path).read_bytes()
        await sandbox.files.write(sandbox_path, content)
        self._file_registries[run_id][local_path] = sandbox_path

    async def download_file(self, run_id: UUID, sandbox_path: str) -> bytes:
        """Download a file from sandbox for a run."""
        sandbox = self._get_sandbox(run_id)

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
                    f"Sandbox timeout/not found when downloading file {sandbox_path} for run_id={run_id}: {e}. "
                    f"Sandbox may have timed out during execution."
                )
                raise RuntimeError(
                    f"Sandbox timed out or was not found when downloading {sandbox_path}. "
                    f"Original error: {e}"
                ) from e
            raise

    async def list_files(self, run_id: UUID, sandbox_dir: str = "/workspace") -> list[str]:
        """List files in sandbox directory recursively for a run."""
        sandbox = self._get_sandbox(run_id)

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
                    f"Sandbox timeout/not found when listing files for run_id={run_id}: {e}. "
                    f"Sandbox may have timed out during execution."
                )
                return []
            raise

    async def download_all_outputs(self, run_id: UUID, output_dir: Path) -> list[DownloadedFile]:
        """Download all files from /workspace to output_dir for a run.

        Handles sandbox timeout gracefully - if sandbox timed out, returns empty list
        and logs a warning.
        """
        try:
            files = await self.list_files(run_id, "/workspace")
            downloaded: list[DownloadedFile] = []

            for file_path in files:
                try:
                    content = await self.download_file(run_id, file_path)
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
                    # Re-raise RuntimeError from download_file (timeout case)
                    # but continue trying other files
                    logger.warning(f"Failed to download {file_path}: {e}")
                    continue

            return downloaded
        except Exception as e:
            error_msg = str(e).lower()
            if "timeout" in error_msg or "sandbox was not found" in error_msg:
                logger.error(
                    f"Sandbox timeout/not found when downloading outputs for run_id={run_id}: {e}. "
                    f"Sandbox may have timed out during execution. No outputs downloaded."
                )
                return []
            raise

    def register_created_file(self, run_id: UUID, sandbox_path: str) -> None:
        """Register a file created by a tool for a run."""
        self._ensure_registries(run_id)
        self._created_files_registry[run_id].add(sandbox_path)

    def get_sandbox_path(self, run_id: UUID, local_path: str) -> str | None:
        """Get sandbox path for a local path if it exists in registry for a run."""
        if run_id not in self._file_registries:
            return None
        return self._file_registries[run_id].get(local_path)

    def get_sandbox(self, run_id: UUID) -> AsyncSandbox | None:
        """Get sandbox instance for a run (returns None if not created)."""
        return self._sandboxes.get(run_id)

    async def terminate(self, run_id: UUID) -> None:
        """Terminate sandbox for a run (idempotent). Always clears registry even if kill() fails."""
        # Use pop() to safely remove - returns None if not present
        sandbox = self._sandboxes.pop(run_id, None)
        if sandbox is None:
            logger.warning(
                f"Sandbox not found for run_id={run_id}. Already terminated or never created."
            )
            # Already terminated or never created - just clean up registries
            self._file_registries.pop(run_id, None)
            self._created_files_registry.pop(run_id, None)
            self._skills_packages.pop(run_id, None)
            return

        try:
            await sandbox.kill()
        except Exception as e:
            # Log but continue - we want to clear the reference even if kill fails
            print(f"Warning: Error killing sandbox for run_id={run_id}: {e}")
        finally:
            # Always clear registries to prevent reuse
            self._file_registries.pop(run_id, None)
            self._created_files_registry.pop(run_id, None)
            self._skills_packages.pop(run_id, None)
