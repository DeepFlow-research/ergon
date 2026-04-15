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
    title: str
    url: str
    summary: str
    published_date: str | None = None
    text_excerpt: str = Field(
        description="Up to 25 000 chars of extracted page text",
    )


class SearchSuccess(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["success"] = "success"
    query: str
    results: list[SearchHit]
    latency_ms: float = Field(ge=0)


class SearchFailure(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["failure"] = "failure"
    query: str
    reason: Literal["timeout", "provider_error", "rate_limit", "auth", "unknown"]
    detail: str
    latency_ms: float = Field(ge=0)


SearchResponse = SearchSuccess | SearchFailure


# ---------------------------------------------------------------------------
# Exa document fetch
# ---------------------------------------------------------------------------


class DocumentSuccess(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["success"] = "success"
    url: str
    title: str
    text: str
    word_count: int = Field(ge=0)
    published_date: str | None = None
    latency_ms: float = Field(ge=0)


class DocumentFailure(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["failure"] = "failure"
    url: str
    reason: Literal["timeout", "http_error", "parse_failed", "empty", "unknown"]
    detail: str
    status_code: int | None = None
    latency_ms: float = Field(ge=0)


DocumentResponse = DocumentSuccess | DocumentFailure


# ---------------------------------------------------------------------------
# Exa Q&A
# ---------------------------------------------------------------------------


class QASource(BaseModel):
    model_config = ConfigDict(frozen=True)
    url: str
    title: str


class QASuccess(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["success"] = "success"
    question: str
    answer: str
    sources: list[QASource]
    latency_ms: float = Field(ge=0)


class QAFailure(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["failure"] = "failure"
    question: str
    reason: Literal["timeout", "provider_error", "rate_limit", "auth", "unknown"]
    detail: str
    latency_ms: float = Field(ge=0)


QAResponse = QASuccess | QAFailure


# ---------------------------------------------------------------------------
# Report write / edit
# ---------------------------------------------------------------------------


class ReportWriteSuccess(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["success"] = "success"
    path: str
    bytes_written: int = Field(ge=0)
    latency_ms: float = Field(ge=0)


class ReportWriteFailure(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["failure"] = "failure"
    path: str
    reason: Literal["io_error", "path_disallowed", "unknown"]
    detail: str
    latency_ms: float = Field(ge=0)


ReportWriteResponse = ReportWriteSuccess | ReportWriteFailure


# ---------------------------------------------------------------------------
# Report read
# ---------------------------------------------------------------------------


class ReportReadSuccess(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["success"] = "success"
    path: str
    content: str
    size_bytes: int = Field(ge=0)
    latency_ms: float = Field(ge=0)


class ReportReadFailure(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["failure"] = "failure"
    path: str
    reason: Literal["not_found", "io_error", "path_disallowed", "unknown"]
    detail: str
    latency_ms: float = Field(ge=0)


ReportReadResponse = ReportReadSuccess | ReportReadFailure
