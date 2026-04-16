"""Discriminated-union response DTOs for ResearchRubrics toolkit skills.

Each Exa tool and report-drafting tool returns a ``kind``-tagged union so
the training loop can distinguish success from failure without inspecting
free-text fields.  Latency is populated by the sandbox skill handler.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Exa search
# ---------------------------------------------------------------------------


class SearchHit(BaseModel):
    model_config = ConfigDict(frozen=True)
    title: str = Field(description="Page title as returned by Exa.")
    url: str = Field(description="Canonical URL of the page.")
    summary: str = Field(
        description="Short Exa-produced summary of the page; may be empty.",
    )
    published_date: str | None = Field(
        default=None,
        description="Publication date string from Exa; ``None`` when unavailable.",
    )
    text_excerpt: str = Field(
        description="Up to 25 000 chars of extracted page text.",
    )


class SearchSuccess(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["success"] = "success"
    query: str = Field(description="The query string the worker submitted.")
    results: list[SearchHit] = Field(
        description="Ranked search results; empty list is a legitimate success.",
    )
    latency_ms: float = Field(
        ge=0,
        description="Wall-clock latency of the search call in milliseconds.",
    )


class SearchFailure(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["failure"] = "failure"
    query: str = Field(description="The query string the worker submitted.")
    reason: Literal["timeout", "provider_error", "rate_limit", "auth", "unknown"] = Field(
        description="Machine-readable failure category for training signal.",
    )
    detail: str = Field(description="Human-readable failure detail from the handler.")
    latency_ms: float = Field(
        ge=0,
        description="Wall-clock latency up to the point of failure.",
    )


SearchResponse = SearchSuccess | SearchFailure


# ---------------------------------------------------------------------------
# Exa document fetch
# ---------------------------------------------------------------------------


class DocumentSuccess(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["success"] = "success"
    url: str = Field(description="URL that was fetched.")
    title: str = Field(description="Document title extracted from the page.")
    text: str = Field(description="Full extracted text.")
    word_count: int = Field(ge=0, description="Word count of ``text``.")
    published_date: str | None = Field(
        default=None,
        description="Publication date string if Exa returned one.",
    )
    latency_ms: float = Field(
        ge=0,
        description="Wall-clock latency of the fetch in milliseconds.",
    )


class DocumentFailure(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["failure"] = "failure"
    url: str = Field(description="URL the worker attempted to fetch.")
    reason: Literal["timeout", "http_error", "parse_failed", "empty", "unknown"] = Field(
        description="Machine-readable failure category.",
    )
    detail: str = Field(description="Human-readable failure detail.")
    status_code: int | None = Field(
        default=None,
        description="HTTP status code if ``reason == 'http_error'``; ``None`` otherwise.",
    )
    latency_ms: float = Field(
        ge=0,
        description="Wall-clock latency up to the point of failure.",
    )


DocumentResponse = DocumentSuccess | DocumentFailure


# ---------------------------------------------------------------------------
# Exa Q&A
# ---------------------------------------------------------------------------


class QASource(BaseModel):
    model_config = ConfigDict(frozen=True)
    url: str = Field(description="Source URL cited by Exa's answer.")
    title: str = Field(description="Page title of the cited source.")


class QASuccess(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["success"] = "success"
    question: str = Field(description="The question the worker asked.")
    answer: str = Field(description="Exa's synthesised answer text.")
    sources: list[QASource] = Field(
        description="Sources Exa cited in the answer; may be empty for low-confidence answers.",
    )
    latency_ms: float = Field(
        ge=0,
        description="Wall-clock latency of the Q&A call in milliseconds.",
    )


class QAFailure(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["failure"] = "failure"
    question: str = Field(description="The question the worker asked.")
    reason: Literal["timeout", "provider_error", "rate_limit", "auth", "unknown"] = Field(
        description="Machine-readable failure category.",
    )
    detail: str = Field(description="Human-readable failure detail.")
    latency_ms: float = Field(
        ge=0,
        description="Wall-clock latency up to the point of failure.",
    )


QAResponse = QASuccess | QAFailure


# ---------------------------------------------------------------------------
# Report write / edit
# ---------------------------------------------------------------------------


class ReportWriteSuccess(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["success"] = "success"
    path: str = Field(description="Sandbox path the report was written to.")
    bytes_written: int = Field(ge=0, description="Number of bytes written.")
    latency_ms: float = Field(
        ge=0,
        description="Wall-clock latency of the write in milliseconds.",
    )


class ReportWriteFailure(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["failure"] = "failure"
    path: str = Field(description="Sandbox path the worker attempted to write.")
    reason: Literal["io_error", "path_disallowed", "unknown"] = Field(
        description="Machine-readable failure category.",
    )
    detail: str = Field(description="Human-readable failure detail.")
    latency_ms: float = Field(
        ge=0,
        description="Wall-clock latency up to the point of failure.",
    )


ReportWriteResponse = ReportWriteSuccess | ReportWriteFailure


# ---------------------------------------------------------------------------
# Report read
# ---------------------------------------------------------------------------


class ReportReadSuccess(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["success"] = "success"
    path: str = Field(description="Sandbox path that was read.")
    content: str = Field(description="Full file contents as UTF-8 text.")
    size_bytes: int = Field(ge=0, description="Size of the file in bytes.")
    latency_ms: float = Field(
        ge=0,
        description="Wall-clock latency of the read in milliseconds.",
    )


class ReportReadFailure(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["failure"] = "failure"
    path: str = Field(description="Sandbox path the worker attempted to read.")
    reason: Literal["not_found", "io_error", "path_disallowed", "unknown"] = Field(
        description="Machine-readable failure category.",
    )
    detail: str = Field(description="Human-readable failure detail.")
    latency_ms: float = Field(
        ge=0,
        description="Wall-clock latency up to the point of failure.",
    )


ReportReadResponse = ReportReadSuccess | ReportReadFailure
