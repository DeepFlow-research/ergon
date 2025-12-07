"""Pydantic response models for tool outputs."""

from pydantic import BaseModel, Field


class ToolResponse(BaseModel):
    """Base response model for tools."""

    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")


class ReadPDFResponse(ToolResponse):
    """Response from read_pdf tool."""

    text: str | None = Field(default=None, description="Extracted text with page markers")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "text": "--- Page 1 ---\nDocument content here...\n\n--- Page 2 ---\nMore content...",
                "error": None,
            }
        }


class CreateDocxResponse(ToolResponse):
    """Response from create_docx tool."""

    output_path: str | None = Field(default=None, description="Path to created DOCX file")
    file_size: int | None = Field(default=None, description="Size of created file in bytes")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "output_path": "/workspace/report.docx",
                "file_size": 15234,
                "error": None,
            }
        }


class ReadExcelResponse(ToolResponse):
    """Response from read_excel tool."""

    sheet_name: str | None = Field(default=None, description="Name of the sheet that was read")
    num_rows: int | None = Field(default=None, description="Total number of rows")
    num_cols: int | None = Field(default=None, description="Total number of columns")
    data: list[list] | None = Field(
        default=None, description="2D array of cell values (rows and columns)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "sheet_name": "Sheet1",
                "num_rows": 10,
                "num_cols": 5,
                "data": [["Header1", "Header2"], ["Value1", "Value2"]],
                "error": None,
            }
        }


class CreateExcelResponse(ToolResponse):
    """Response from create_excel tool."""

    output_path: str | None = Field(default=None, description="Path to created Excel file")
    file_size: int | None = Field(default=None, description="Size of created file in bytes")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "output_path": "/workspace/data.xlsx",
                "file_size": 8765,
                "error": None,
            }
        }


class ReadCsvResponse(ToolResponse):
    """Response from read_csv tool."""

    num_rows: int | None = Field(default=None, description="Total number of rows")
    num_cols: int | None = Field(default=None, description="Total number of columns")
    data: list[list] | None = Field(default=None, description="2D array of data (rows and columns)")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "num_rows": 100,
                "num_cols": 3,
                "data": [["Name", "Age", "City"], ["Alice", "30", "NYC"]],
                "error": None,
            }
        }


class CreateCsvResponse(ToolResponse):
    """Response from create_csv tool."""

    output_path: str | None = Field(default=None, description="Path to created CSV file")
    file_size: int | None = Field(default=None, description="Size of created file in bytes")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "output_path": "/workspace/export.csv",
                "file_size": 1234,
                "error": None,
            }
        }


class OcrImageResponse(ToolResponse):
    """Response from ocr_image tool."""

    text: str | None = Field(default=None, description="Extracted text from image")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "text": "Extracted text from image",
                "error": None,
            }
        }
