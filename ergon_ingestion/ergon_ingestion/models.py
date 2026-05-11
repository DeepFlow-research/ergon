"""Pydantic ingestion contracts emitted by source parsers."""

from collections.abc import Iterator
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

ImportCompatibility = Literal["safe", "conditional", "not_now"]
ReducerKind = Literal["original", "recovered", "regrade", "diagnostic"]


class ImportSource(BaseModel):
    """Local source selected for a named dataset importer."""

    model_config = ConfigDict(frozen=True)

    dataset: str
    input_path: Path
    batch_id: str
    source_url: str | None = None
    source_version_ref: str | None = None
    source_license: str | None = None
    redistribution_class: str = "metadata-plus-fetch"


class ParsedAnnotation(BaseModel):
    """Namespaced metadata to attach to an imported run's root node."""

    model_config = ConfigDict(frozen=True)

    namespace: str
    payload: dict = Field(default_factory=dict)


class ParsedEvent(BaseModel):
    """Ordered source-observed event in an imported run."""

    model_config = ConfigDict(frozen=True)

    sequence: int
    event_type: str
    payload: dict = Field(default_factory=dict)
    worker_binding_key: str = "imported"


class ParsedResource(BaseModel):
    """Source artifact or materialized payload associated with a run."""

    model_config = ConfigDict(frozen=True)

    name: str
    kind: str
    mime_type: str
    path: Path | None = None
    payload: dict | str | None = None


class ParsedDrop(BaseModel):
    """Declared reducer loss or unavailable source field."""

    model_config = ConfigDict(frozen=True)

    loss_class: str
    reason: str
    dropped_field_path: str | None = None
    affected_analysis: str | None = None
    declaration_kind: str = "author_declared"
    evidence: dict = Field(default_factory=dict)


class ParsedReducer(BaseModel):
    """Reducer output plus compact footprint declarations."""

    model_config = ConfigDict(frozen=True)

    name: str
    kind: ReducerKind
    output: dict = Field(default_factory=dict)
    implementation_ref: str | None = None
    fields_read: list[str] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)
    aggregation: dict = Field(default_factory=dict)
    drops: list[ParsedDrop] = Field(default_factory=list)


class ParsedRun(BaseModel):
    """Database-independent imported run representation."""

    model_config = ConfigDict(frozen=True)

    source_run_id: str
    instance_key: str
    description: str
    schema_fit_class: str
    observed_fields: dict = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    annotations: list[ParsedAnnotation] = Field(default_factory=list)
    events: list[ParsedEvent] = Field(default_factory=list)
    resources: list[ParsedResource] = Field(default_factory=list)
    reducers: list[ParsedReducer] = Field(default_factory=list)


class ValidationReport(BaseModel):
    """Result of validating a local source before import."""

    model_config = ConfigDict(frozen=True)

    dataset: str
    input_path: Path
    ok: bool
    planned_runs: int | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ImporterInfo(BaseModel):
    """Static metadata for CLI listing and descriptions."""

    model_config = ConfigDict(frozen=True)

    slug: str
    display_name: str
    schema_fit_class: str
    supported_formats: list[str]
    export_claim: ImportCompatibility
    paper_result_ids: list[str] = Field(default_factory=list)
    default_reducers: list[str] = Field(default_factory=list)


class DatasetImporter(Protocol):
    """Protocol implemented by named public artifact importers."""

    info: ImporterInfo

    def validate(self, source: ImportSource) -> ValidationReport: ...

    def iter_runs(self, source: ImportSource) -> Iterator[ParsedRun]: ...
