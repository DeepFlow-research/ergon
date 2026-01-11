"""Read report draft skill - reads content from a markdown file."""

from pathlib import Path

from .responses import ReadReportDraftResponse


async def main(
    file_path: str = "/workspace/final_output/report.md",
) -> ReadReportDraftResponse:
    """
    Read content from a markdown report file.

    Args:
        file_path: Path to the file to read (default: /workspace/final_output/report.md)

    Returns:
        ReadReportDraftResponse with file content
    """
    try:
        path = Path(file_path)

        if not path.exists():
            return ReadReportDraftResponse(
                success=False,
                error=f"File not found: {file_path}",
            )

        # Read content
        content = path.read_text(encoding="utf-8")

        return ReadReportDraftResponse(
            success=True,
            file_path=str(path.absolute()),
            content=content,
            bytes_read=len(content.encode("utf-8")),
        )

    except Exception as e:
        return ReadReportDraftResponse(
            success=False,
            error=f"Error reading report draft: {str(e)}",
        )
