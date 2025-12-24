"""Write report draft skill - writes/overwrites content to a markdown file."""

from pathlib import Path

from .responses import WriteReportDraftResponse


async def main(
    content: str,
    file_path: str = "/workspace/report_draft.md",
) -> WriteReportDraftResponse:
    """
    Write content to a markdown report draft file.

    Creates or overwrites the file at the specified path.

    Args:
        content: The markdown content to write
        file_path: Path to write the file (default: /workspace/report_draft.md)

    Returns:
        WriteReportDraftResponse with file_path and bytes_written
    """
    try:
        if not content:
            return WriteReportDraftResponse(
                success=False,
                error="Content cannot be empty",
            )

        # Ensure parent directory exists
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        path.write_text(content, encoding="utf-8")

        return WriteReportDraftResponse(
            success=True,
            file_path=str(path.absolute()),
            bytes_written=len(content.encode("utf-8")),
        )

    except Exception as e:
        return WriteReportDraftResponse(
            success=False,
            error=f"Error writing report draft: {str(e)}",
        )
