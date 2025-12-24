"""Pydantic response models for ResearchRubrics skills."""

from pydantic import BaseModel, Field


class ExaSearchResult(BaseModel):
    """Single search result from Exa."""

    title: str = Field(description="Page title")
    url: str = Field(description="Page URL")
    summary: str | None = Field(default=None, description="Summary/snippet of the page")
    content: str | None = Field(
        default=None, description="Extracted text content (truncated to 5000 chars)"
    )
    published_date: str | None = Field(default=None, description="Publication date if available")


class ExaSearchResponse(BaseModel):
    """Response from exa_search skill."""

    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    query: str | None = Field(default=None, description="The search query that was executed")
    results: list[ExaSearchResult] | None = Field(
        default=None, description="List of search results"
    )


class ExaQAResponse(BaseModel):
    """Response from exa_qa skill."""

    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    question: str | None = Field(default=None, description="The question that was asked")
    answer: str | None = Field(default=None, description="The answer extracted from sources")
    sources: list[dict[str, str]] | None = Field(
        default=None, description="List of source dicts with 'url' and 'title' keys"
    )


class ExaGetContentResponse(BaseModel):
    """Response from exa_get_content skill."""

    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    url: str | None = Field(default=None, description="URL that was fetched")
    title: str | None = Field(default=None, description="Page title")
    content: str | None = Field(default=None, description="Full extracted text content")
    published_date: str | None = Field(default=None, description="Publication date if available")


# ─────────────────────────────────────────────────────────────────
# Report Draft Skills Responses
# ─────────────────────────────────────────────────────────────────


class WriteReportDraftResponse(BaseModel):
    """Response from write_report_draft skill."""

    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    file_path: str | None = Field(default=None, description="Path to the written file")
    bytes_written: int | None = Field(default=None, description="Number of bytes written")


class EditReportDraftResponse(BaseModel):
    """Response from edit_report_draft skill."""

    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    file_path: str | None = Field(default=None, description="Path to the edited file")
    replacements_made: int | None = Field(default=None, description="Number of replacements made")


class ReadReportDraftResponse(BaseModel):
    """Response from read_report_draft skill."""

    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    file_path: str | None = Field(default=None, description="Path to the file that was read")
    content: str | None = Field(default=None, description="Content of the file")
    bytes_read: int | None = Field(default=None, description="Number of bytes read")
