"""GDPEval sandbox operation response models."""

from pydantic import BaseModel, Field


class ReadPDFResponse(BaseModel):
    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None)
    text: str | None = Field(default=None, description="Extracted text with page markers")
    page_count: int | None = Field(default=None)


class CreateDocxResponse(BaseModel):
    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None)
    output_path: str | None = Field(default=None)
    file_size: int | None = Field(default=None, description="Bytes")


class ReadExcelResponse(BaseModel):
    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None)
    sheet_name: str | None = Field(default=None)
    available_sheets: list[str] | None = Field(default=None)
    num_rows: int | None = Field(default=None)
    num_cols: int | None = Field(default=None)
    data: list[list] | None = Field(default=None, description="2-D cell values")


class CreateExcelResponse(BaseModel):
    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None)
    output_path: str | None = Field(default=None)
    file_size: int | None = Field(default=None, description="Bytes")


class ReadCsvResponse(BaseModel):
    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None)
    num_rows: int | None = Field(default=None)
    num_cols: int | None = Field(default=None)
    data: list[list] | None = Field(default=None, description="2-D cell values")


class CreateCsvResponse(BaseModel):
    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None)
    output_path: str | None = Field(default=None)
    file_size: int | None = Field(default=None, description="Bytes")


class OcrImageResponse(BaseModel):
    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None)
    text: str | None = Field(default=None, description="Extracted text from image")


class RunPythonResponse(BaseModel):
    success: bool = Field(description="Whether code executed without errors")
    error: str | None = Field(default=None)
    stdout: str | None = Field(default=None)
    stderr: str | None = Field(default=None)
    return_value: str | None = Field(default=None, description="String repr of return value")


__all__ = [
    "CreateCsvResponse",
    "CreateDocxResponse",
    "CreateExcelResponse",
    "OcrImageResponse",
    "ReadCsvResponse",
    "ReadExcelResponse",
    "ReadPDFResponse",
    "RunPythonResponse",
]
