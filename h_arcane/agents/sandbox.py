"""E2B sandbox lifecycle management for runs."""

from uuid import UUID
from pathlib import Path
from e2b_code_interpreter.code_interpreter_async import AsyncSandbox

from h_arcane.db.models import Resource
from h_arcane.settings import settings

from logging import getLogger

logger = getLogger(__name__)


class SandboxManager:
    """Singleton container managing E2B sandboxes for multiple runs."""

    _instance: "SandboxManager | None" = None
    _sandboxes: dict[UUID, AsyncSandbox] = {}  # run_id -> sandbox
    _file_registries: dict[UUID, dict[str, str]] = {}  # run_id -> {local_path: sandbox_path}
    _created_files_registry: dict[UUID, set[str]] = {}  # run_id -> {sandbox_paths}

    def __new__(cls):
        """Singleton pattern - always return the same instance."""
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

    async def create(self, run_id: UUID) -> None:
        """Create and initialize sandbox for a run (idempotent)."""
        # If sandbox already exists for this run_id, skip creation
        if run_id in self._sandboxes:
            return

        try:
            sandbox = await AsyncSandbox.create(api_key=settings.e2b_api_key)
        except Exception as e:
            raise RuntimeError(f"Failed to create sandbox for run_id={run_id}: {e}") from e

        if not sandbox:
            raise RuntimeError("Sandbox object is None after creation")

        # Store sandbox in registry
        self._sandboxes[run_id] = sandbox
        self._ensure_registries(run_id)

        # Create directory structure using Python code execution
        # This is more reliable than shell commands in E2B sandboxes
        create_dirs_code = """
import os
import stat

dirs = ['/inputs', '/workspace', '/tools']
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

        # Check if directory creation was successful by verifying we can write to them
        if dir_result.error:
            # Clean up sandbox before raising error
            await self.terminate(run_id)
            raise RuntimeError(f"Failed to create directories using Python: {dir_result.error}")

        # Verify directories are writable by attempting to write test files
        try:
            await sandbox.files.write("/inputs/.test_write", b"test")
            await sandbox.files.write("/workspace/.test_write", b"test")
            # Clean up test files
            try:
                await sandbox.commands.run("rm -f /inputs/.test_write /workspace/.test_write")
            except Exception:
                pass  # Cleanup failure is not critical
        except Exception as e:
            # Clean up sandbox before raising error
            await self.terminate(run_id)
            raise RuntimeError(
                f"Directories created but not writable. Python output: {dir_result.logs.stdout if dir_result.logs else 'N/A'}, "
                f"Error: {e}"
            )

        # Install missing tool dependencies
        # E2B default has: numpy, pandas, matplotlib, sklearn, scipy, openpyxl, docx, seaborn, plotly
        # Need: pdfplumber, PyPDF2, reportlab, pytesseract
        logger.info(f"Installing required packages for code rule evaluation (run_id={run_id})...")
        pip_result = await sandbox.commands.run(
            "pip install -q pdfplumber PyPDF2 reportlab pytesseract"
        )
        if pip_result.exit_code != 0:
            # Log installation failure - this is critical for code rules
            error_msg = (
                f"Failed to install required packages (pdfplumber, PyPDF2, reportlab, pytesseract) "
                f"for run_id={run_id}. Exit code: {pip_result.exit_code}. "
                f"Stderr: {pip_result.stderr if pip_result.stderr else 'N/A'}"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        # Verify packages are actually importable
        logger.info(f"Verifying package installation (run_id={run_id})...")
        verify_code = """
import sys
packages = ['pdfplumber', 'PyPDF2', 'reportlab']
missing = []
for pkg in packages:
    try:
        __import__(pkg)
    except ImportError:
        missing.append(pkg)
if missing:
    print(f"MISSING: {', '.join(missing)}", file=sys.stderr)
    sys.exit(1)
print("All packages verified successfully")
"""
        verify_result = await sandbox.run_code(verify_code, language="python", timeout=10)
        # Check for errors using the error attribute (Execution object has error: Optional[ExecutionError])
        if verify_result.error is not None:
            stderr_text = "N/A"
            if verify_result.logs and verify_result.logs.stderr:
                stderr_parts = list(verify_result.logs.stderr)
                stderr_text = "\n".join(stderr_parts) if stderr_parts else "N/A"
            error_msg = (
                f"Package verification failed for run_id={run_id}. "
                f"Error: {verify_result.error}, Stderr: {stderr_text}"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        logger.info(f"Successfully installed and verified all required packages (run_id={run_id})")

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

        content = await sandbox.files.read(sandbox_path)
        # Ensure we return bytes
        if isinstance(content, str):
            return content.encode("utf-8")
        return content

    async def list_files(self, run_id: UUID, sandbox_dir: str = "/workspace") -> list[str]:
        """List files in sandbox directory recursively for a run."""
        sandbox = self._get_sandbox(run_id)

        # Use find command to list files recursively
        result = await sandbox.commands.run(f"find {sandbox_dir} -type f 2>/dev/null || true")
        if result.exit_code != 0:
            return []
        # Parse output - each line is a file path
        files = [line.strip() for line in result.stdout.split("\n") if line.strip()]
        return files

    async def download_all_outputs(
        self, run_id: UUID, output_dir: Path
    ) -> list[dict[str, str | int]]:
        """Download all files from /workspace to output_dir for a run."""
        files = await self.list_files(run_id, "/workspace")
        downloaded = []

        for file_path in files:
            content = await self.download_file(run_id, file_path)
            local_path = output_dir / Path(file_path).name
            local_path.write_bytes(content)
            downloaded.append(
                {
                    "sandbox_path": file_path,
                    "local_path": str(local_path),
                    "size_bytes": len(content),
                }
            )

        return downloaded

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
