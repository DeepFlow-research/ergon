"""ResearchRubrics public sandbox definition."""

from uuid import UUID

from ergon_builtins.sandbox_runtime import E2BSandbox


class ResearchRubricsSandbox(E2BSandbox):
    """Public ResearchRubrics sandbox definition."""

    async def read_report_file(
        self,
        *,
        task_id: UUID,
        workspace_path: str,
        duration_ms: int | None = None,
    ) -> str:
        """Read a report file from the sandbox and emit file-read telemetry."""
        content = await self.read_file(workspace_path)
        return content.decode("utf-8")

    async def write_report_file(
        self,
        *,
        task_id: UUID,
        workspace_path: str,
        content: str,
        duration_ms: int | None = None,
    ) -> None:
        """Write a report file to the sandbox and emit file-write telemetry."""
        await self.write_file(workspace_path, content.encode("utf-8"))
