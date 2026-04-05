"""Create Excel skill - creates Excel spreadsheets."""

import openpyxl
from pathlib import Path

from .responses import CreateExcelResponse


async def main(
    data: list[list], output_path: str, sheet_name: str = "Sheet1"
) -> CreateExcelResponse:
    """
    Create Excel file from 2D array data.

    Args:
        data: 2D array of data (list of rows, each row is list of cells)
        output_path: Path to save Excel file (e.g., "/workspace/data.xlsx")
        sheet_name: Name of the sheet (default: "Sheet1")

    Returns:
        CreateExcelResponse with output_path and file_size
    """
    try:
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        if sheet is None:
            return CreateExcelResponse(success=False, error="Failed to create worksheet")

        sheet.title = sheet_name

        for row_idx, row_data in enumerate(data, start=1):
            for col_idx, cell_value in enumerate(row_data, start=1):
                sheet.cell(row=row_idx, column=col_idx, value=cell_value)

        workbook.save(str(output_path_obj))

        return CreateExcelResponse(
            success=True,
            output_path=str(output_path_obj.absolute()),
            file_size=output_path_obj.stat().st_size,
        )

    except Exception as e:
        return CreateExcelResponse(success=False, error=f"Error creating Excel: {str(e)}")
