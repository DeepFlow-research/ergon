"""Pydantic response models for GDPEval skills.

These models are used both in the VM (by skills) and locally (by toolkits).
Uses relative imports in skills, absolute imports in toolkits.
"""

from pydantic import BaseModel, Field


class ReadPDFResponse(BaseModel):
    """Response from read_pdf skill."""

    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    text: str | None = Field(default=None, description="Extracted text with page markers")
    page_count: int | None = Field(default=None, description="Number of pages in the PDF")


class CreateDocxResponse(BaseModel):
    """Response from create_docx skill."""

    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    output_path: str | None = Field(default=None, description="Path to created DOCX file")
    file_size: int | None = Field(default=None, description="Size of created file in bytes")


class ReadExcelResponse(BaseModel):
    """Response from read_excel skill."""

    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    sheet_name: str | None = Field(default=None, description="Name of the sheet that was read")
    available_sheets: list[str] | None = Field(
        default=None, description="List of all available sheet names in the workbook"
    )
    num_rows: int | None = Field(default=None, description="Total number of rows")
    num_cols: int | None = Field(default=None, description="Total number of columns")
    data: list[list] | None = Field(
        default=None, description="2D array of cell values (rows and columns)"
    )


class CreateExcelResponse(BaseModel):
    """Response from create_excel skill."""

    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    output_path: str | None = Field(default=None, description="Path to created Excel file")
    file_size: int | None = Field(default=None, description="Size of created file in bytes")


class ReadCsvResponse(BaseModel):
    """Response from read_csv skill."""

    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    num_rows: int | None = Field(default=None, description="Total number of rows")
    num_cols: int | None = Field(default=None, description="Total number of columns")
    data: list[list] | None = Field(default=None, description="2D array of data (rows and columns)")


class CreateCsvResponse(BaseModel):
    """Response from create_csv skill."""

    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    output_path: str | None = Field(default=None, description="Path to created CSV file")
    file_size: int | None = Field(default=None, description="Size of created file in bytes")


class OcrImageResponse(BaseModel):
    """Response from ocr_image skill."""

    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    text: str | None = Field(default=None, description="Extracted text from image")


class RunPythonResponse(BaseModel):
    """Response from run_python skill."""

    success: bool = Field(description="Whether the code executed without errors")
    error: str | None = Field(default=None, description="Error message if execution failed")
    stdout: str | None = Field(default=None, description="Standard output from execution")
    stderr: str | None = Field(default=None, description="Standard error from execution")
    return_value: str | None = Field(
        default=None, description="String representation of return value"
    )
