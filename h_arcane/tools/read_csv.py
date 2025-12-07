"""Read CSV tool - works in sandbox or locally."""

import csv
from pathlib import Path

from h_arcane.tools.responses import ReadCsvResponse


async def read_csv(file_path: str, max_rows: int | None = None) -> ReadCsvResponse:
    """
    Read data from CSV file.

    Args:
        file_path: Path to CSV file (e.g., "/inputs/data.csv" or "/workspace/export.csv")
        max_rows: Optional maximum rows to read

    Returns:
        ReadCsvResponse with data, num_rows, num_cols or error message

    Example:
        ```python
        result = await read_csv("/inputs/data.csv", max_rows=100)
        if result.success:
            print(f"Read {result.num_rows} rows, {result.num_cols} columns")
            print(result.data[0])  # First row
        ```
    """
    try:
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            return ReadCsvResponse(
                success=False, error="CSV file not found", num_rows=None, num_cols=None, data=None
            )

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
            error=None,
        )

    except Exception as e:
        return ReadCsvResponse(
            success=False,
            error=f"Error reading CSV: {str(e)}",
            num_rows=None,
            num_cols=None,
            data=None,
        )
