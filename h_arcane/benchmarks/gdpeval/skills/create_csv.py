"""Create CSV skill - creates CSV files."""

import csv
from pathlib import Path

from .responses import CreateCsvResponse


async def main(data: list[list], output_path: str) -> CreateCsvResponse:
    """
    Create CSV file from 2D array data.

    Args:
        data: 2D array of data (list of rows, each row is list of cells)
        output_path: Path to save CSV file (e.g., "/workspace/export.csv")

    Returns:
        CreateCsvResponse with output_path and file_size
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
        )

    except Exception as e:
        return CreateCsvResponse(success=False, error=f"Error creating CSV: {str(e)}")
