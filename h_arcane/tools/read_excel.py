"""Read Excel tool - works in sandbox or locally."""

import openpyxl
from pathlib import Path

from h_arcane.tools.responses import ReadExcelResponse


async def read_excel(file_path: str, sheet_name: str | None = None) -> ReadExcelResponse:
    """
    Read data from Excel file.

    Args:
        file_path: Path to Excel file (e.g., "/inputs/data.xlsx" or "/workspace/report.xlsx")
        sheet_name: Optional sheet name (defaults to active sheet)

    Returns:
        ReadExcelResponse with data, sheet_name, num_rows, num_cols or error message

    Example:
        ```python
        result = await read_excel("/inputs/data.xlsx", sheet_name="Sheet1")
        if result.success:
            print(f"Read {result.num_rows} rows from {result.sheet_name}")
            print(result.data[0])  # First row
        ```
    """
    try:
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            return ReadExcelResponse(
                success=False,
                error="Excel file not found",
                sheet_name=None,
                num_rows=None,
                num_cols=None,
                data=None,
            )

        workbook = openpyxl.load_workbook(file_path, data_only=True)

        if sheet_name:
            if sheet_name not in workbook.sheetnames:
                return ReadExcelResponse(
                    success=False,
                    error=f"Sheet '{sheet_name}' not found",
                    sheet_name=None,
                    num_rows=None,
                    num_cols=None,
                    data=None,
                )
            sheet = workbook[sheet_name]
        else:
            sheet = workbook.active

        if sheet is None:
            return ReadExcelResponse(
                success=False,
                error="No active worksheet found",
                sheet_name=None,
                num_rows=None,
                num_cols=None,
                data=None,
            )

        data = []
        for row in sheet.iter_rows(values_only=True):
            row_data = [
                ""
                if cell is None
                else str(cell)
                if not isinstance(cell, (str, int, float, bool))
                else cell
                for cell in row
            ]
            data.append(row_data)

        return ReadExcelResponse(
            success=True,
            sheet_name=sheet.title,
            num_rows=len(data),
            num_cols=len(data[0]) if data else 0,
            data=data,
            error=None,
        )

    except Exception as e:
        return ReadExcelResponse(
            success=False,
            error=f"Error reading Excel: {str(e)}",
            sheet_name=None,
            num_rows=None,
            num_cols=None,
            data=None,
        )
