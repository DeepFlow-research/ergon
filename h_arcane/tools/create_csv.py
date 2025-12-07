"""Create CSV tool - works in sandbox or locally."""

import csv
from pathlib import Path

from h_arcane.tools.responses import CreateCsvResponse


async def create_csv(data: list[list], output_path: str) -> CreateCsvResponse:
    """
    Create CSV file from 2D array data.

    Args:
        data: 2D array of data (list of rows, each row is list of cells)
        output_path: Path to save CSV file (e.g., "/workspace/export.csv")

    Returns:
        CreateCsvResponse with output_path and file_size or error message

    Example:
        ```python
        result = await create_csv(
            data=[["Name", "Age"], ["Alice", "30"], ["Bob", "25"]],
            output_path="/workspace/people.csv"
        )
        if result.success:
            print(f"Created: {result.output_path}, size: {result.file_size} bytes")
        ```
    """
    try:
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(data)

        return CreateCsvResponse(
            success=True,
            output_path=str(output_path_obj.absolute()),
            file_size=output_path_obj.stat().st_size,
            error=None,
        )
    except Exception as e:
        return CreateCsvResponse(
            success=False, error=f"Error creating CSV: {str(e)}", output_path=None, file_size=None
        )
