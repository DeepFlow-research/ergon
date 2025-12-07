"""E2B sandbox lifecycle management for runs."""

from uuid import UUID
from pathlib import Path
from e2b_code_interpreter.code_interpreter_async import AsyncSandbox

from h_arcane.db.models import Resource
from h_arcane.settings import settings


class SandboxManager:
    """Manages E2B sandbox lifecycle for a single run."""

    def __init__(self, run_id: UUID):
        self.run_id = run_id
        self.sandbox: AsyncSandbox | None = None
        self._file_registry: dict[str, str] = {}  # local_path -> sandbox_path
        self._created_files: set[str] = set()  # sandbox paths created by tools

    async def create(self) -> None:
        """Create and initialize sandbox."""
        self.sandbox = await AsyncSandbox.create(api_key=settings.e2b_api_key)

        # Create directory structure
        await self.sandbox.commands.run("mkdir -p /inputs")
        await self.sandbox.commands.run("mkdir -p /workspace")

        # Install missing tool dependencies
        # E2B default has: numpy, pandas, matplotlib, sklearn, scipy, openpyxl, docx, seaborn, plotly
        # Need: pdfplumber, PyPDF2, reportlab, pytesseract
        await self.sandbox.commands.run("pip install -q pdfplumber PyPDF2 reportlab pytesseract")

    async def upload_inputs(self, resources: list[Resource]) -> None:
        """Upload input resources to /inputs/."""
        if not self.sandbox:
            raise RuntimeError("Sandbox not created. Call create() first.")

        for resource in resources:
            sandbox_path = f"/inputs/{resource.name}"
            content = resource.load_content()
            await self.sandbox.files.write(sandbox_path, content)
            self._file_registry[resource.file_path] = sandbox_path

    async def upload_file(self, local_path: str, sandbox_path: str) -> None:
        """Upload a single file to sandbox."""
        if not self.sandbox:
            raise RuntimeError("Sandbox not created. Call create() first.")

        content = Path(local_path).read_bytes()
        await self.sandbox.files.write(sandbox_path, content)
        self._file_registry[local_path] = sandbox_path

    async def download_file(self, sandbox_path: str) -> bytes:
        """Download a file from sandbox."""
        if not self.sandbox:
            raise RuntimeError("Sandbox not created. Call create() first.")

        content = await self.sandbox.files.read(sandbox_path)
        # Ensure we return bytes
        if isinstance(content, str):
            return content.encode("utf-8")
        return content

    async def list_files(self, sandbox_dir: str = "/workspace") -> list[str]:
        """List files in sandbox directory recursively."""
        if not self.sandbox:
            raise RuntimeError("Sandbox not created. Call create() first.")

        # Use find command to list files recursively
        result = await self.sandbox.commands.run(f"find {sandbox_dir} -type f 2>/dev/null || true")
        if result.exit_code != 0:
            return []
        # Parse output - each line is a file path
        files = [line.strip() for line in result.stdout.split("\n") if line.strip()]
        return files

    async def download_all_outputs(self, output_dir: Path) -> list[dict[str, str | int]]:
        """Download all files from /workspace to output_dir."""
        files = await self.list_files("/workspace")
        downloaded = []

        for file_path in files:
            content = await self.download_file(file_path)
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

    def register_created_file(self, sandbox_path: str) -> None:
        """Register a file created by a tool (for tracking)."""
        self._created_files.add(sandbox_path)

    def get_sandbox_path(self, local_path: str) -> str | None:
        """Get sandbox path for a local path if it exists in registry."""
        return self._file_registry.get(local_path)

    async def terminate(self) -> None:
        """Terminate sandbox."""
        if self.sandbox:
            await self.sandbox.kill()
            self.sandbox = None
