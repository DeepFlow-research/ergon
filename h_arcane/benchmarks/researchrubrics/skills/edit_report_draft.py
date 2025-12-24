"""Edit report draft skill - search and replace in a markdown file."""

from pathlib import Path

from .responses import EditReportDraftResponse


async def main(
    old_string: str,
    new_string: str,
    file_path: str = "/workspace/report_draft.md",
) -> EditReportDraftResponse:
    """
    Edit content in a markdown report draft file using search and replace.

    Replaces all occurrences of old_string with new_string.

    Args:
        old_string: The text to find and replace
        new_string: The text to replace with
        file_path: Path to the file to edit (default: /workspace/report_draft.md)

    Returns:
        EditReportDraftResponse with file_path and replacements_made count
    """
    try:
        path = Path(file_path)

        if not path.exists():
            return EditReportDraftResponse(
                success=False,
                error=f"File not found: {file_path}",
            )

        # Read current content
        content = path.read_text(encoding="utf-8")

        # Count replacements
        count = content.count(old_string)

        if count == 0:
            return EditReportDraftResponse(
                success=False,
                error=f"String not found in file: '{old_string[:50]}...' (truncated)",
            )

        # Replace all occurrences
        new_content = content.replace(old_string, new_string)

        # Write back
        path.write_text(new_content, encoding="utf-8")

        return EditReportDraftResponse(
            success=True,
            file_path=str(path.absolute()),
            replacements_made=count,
        )

    except Exception as e:
        return EditReportDraftResponse(
            success=False,
            error=f"Error editing report draft: {str(e)}",
        )
