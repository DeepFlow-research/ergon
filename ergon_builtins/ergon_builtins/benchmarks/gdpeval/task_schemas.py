"""GDP-specific task data shapes.

Pydantic models for workflow configuration, dataset references, task
instances, and sandbox operation response types used throughout the
GDPEval benchmark.
"""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class GDPDatasetRef(BaseModel):
    """Pointer to the on-disk GDP evaluation dataset."""

    parquet_path: str = Field(description="Path to gdpeval.parquet")
    reference_dir: str = Field(description="Directory containing per-task reference files")
    rubric_file: str = Field(description="Path to staged rubrics JSONL file")


class GDPTaskConfig(BaseModel):
    """Configuration for a single GDP evaluation task."""

    task_id: str = Field(description="GDPEval task identifier (e.g. 'task_001')")
    workflow_type: str = Field(
        default="document_processing",
        description="Workflow category for the task",
    )
    category: str = Field(default="", description="High-level task category")
    reference_files: list[str] = Field(
        default_factory=list,
        description="Paths to reference / input files",
    )
    dataset_ref: GDPDatasetRef | None = Field(
        default=None,
        description="Optional pointer to the full dataset",
    )


class GDPTaskInstance(BaseModel):
    """A fully loaded GDP task ready for execution."""

    task_id: str
    task_description: str
    reference_files: list[Path] = Field(default_factory=list)
    category: str = ""  # slopcop: ignore[no-str-empty-default]
    rubric_data: dict[str, Any] = Field(  # slopcop: ignore[no-typing-any]
        default_factory=dict,
        description="Raw rubric JSON blob for this task",
    )


# ---------------------------------------------------------------------------
# Sandbox operation response models
# ---------------------------------------------------------------------------
# These are shared between the toolkit (caller side) and the sandbox skills
# (VM side).  Keeping them here avoids a circular dependency.


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
