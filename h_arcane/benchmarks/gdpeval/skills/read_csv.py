"""Read CSV skill - reads data from CSV files."""

import csv
from pathlib import Path

from .responses import ReadCsvResponse


async def main(file_path: str, max_rows: int | None = None) -> ReadCsvResponse:
    """
    Read data from CSV file.

    Args:
        file_path: Path to CSV file (e.g., "/inputs/data.csv")
        max_rows: Optional maximum rows to read

    Returns:
        ReadCsvResponse with data, num_rows, num_cols
    """
    try:
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            return ReadCsvResponse(success=False, error=f"CSV file not found: {file_path}")

        data = []
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row_idx, row in enumerate(reader, start=1):
                if max_rows and row_idx > max_rows:
                    break
                data.append(row)

        return ReadCsvResponse(
            success=True,
            num_rows=len(data),
            num_cols=len(data[0]) if data else 0,
            data=data,
        )

    except Exception as e:
        return ReadCsvResponse(success=False, error=f"Error reading CSV: {str(e)}")
