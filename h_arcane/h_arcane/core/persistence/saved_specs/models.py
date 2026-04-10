"""Saved-spec tables: product-facing, editable, store identity and
user-facing configuration — not serialized Python objects.
"""

from datetime import datetime
from uuid import UUID, uuid4

from h_arcane.core.utils import utcnow as _utcnow
from pydantic import model_validator
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

# ---------------------------------------------------------------------------
# SavedBenchmarkSpec
# ---------------------------------------------------------------------------


class SavedBenchmarkSpec(SQLModel, table=True):
    __tablename__ = "saved_benchmark_specs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    slug: str = Field(index=True, unique=True)
    benchmark_type: str = Field(index=True)
    title: str
    description: str | None = None
    metadata_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    # -- JSON accessor: metadata_json --

    def parsed_metadata(self) -> dict[str, object]:
        return self.__class__._parse_metadata(self.metadata_json)

    @classmethod
    def _parse_metadata(cls, data: dict) -> dict[str, object]:
        if not isinstance(data, dict):
            raise ValueError(f"metadata_json must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_metadata_json(self) -> "SavedBenchmarkSpec":
        self.__class__._parse_metadata(self.metadata_json)
        return self


# ---------------------------------------------------------------------------
# SavedWorkerSpec
# ---------------------------------------------------------------------------


class SavedWorkerSpec(SQLModel, table=True):
    __tablename__ = "saved_worker_specs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    slug: str = Field(index=True, unique=True)
    worker_type: str = Field(index=True)
    model_target: str
    title: str
    description: str | None = None
    metadata_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    # -- JSON accessor: metadata_json --

    def parsed_metadata(self) -> dict[str, object]:
        return self.__class__._parse_metadata(self.metadata_json)

    @classmethod
    def _parse_metadata(cls, data: dict) -> dict[str, object]:
        if not isinstance(data, dict):
            raise ValueError(f"metadata_json must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_metadata_json(self) -> "SavedWorkerSpec":
        self.__class__._parse_metadata(self.metadata_json)
        return self


# ---------------------------------------------------------------------------
# SavedEvaluatorSpec
# ---------------------------------------------------------------------------


class SavedEvaluatorSpec(SQLModel, table=True):
    __tablename__ = "saved_evaluator_specs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    slug: str = Field(index=True, unique=True)
    evaluator_type: str = Field(index=True)
    title: str
    description: str | None = None
    metadata_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    # -- JSON accessor: metadata_json --

    def parsed_metadata(self) -> dict[str, object]:
        return self.__class__._parse_metadata(self.metadata_json)

    @classmethod
    def _parse_metadata(cls, data: dict) -> dict[str, object]:
        if not isinstance(data, dict):
            raise ValueError(f"metadata_json must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_metadata_json(self) -> "SavedEvaluatorSpec":
        self.__class__._parse_metadata(self.metadata_json)
        return self


# ---------------------------------------------------------------------------
# SavedExperimentTemplate
# ---------------------------------------------------------------------------


class SavedExperimentTemplate(SQLModel, table=True):
    __tablename__ = "saved_experiment_templates"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    slug: str = Field(index=True, unique=True)
    title: str
    description: str | None = None
    template_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    # -- JSON accessor: template_json --

    def parsed_template(self) -> dict[str, object]:
        return self.__class__._parse_template(self.template_json)

    @classmethod
    def _parse_template(cls, data: dict) -> dict[str, object]:
        if not isinstance(data, dict):
            raise ValueError(f"template_json must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_template_json(self) -> "SavedExperimentTemplate":
        self.__class__._parse_template(self.template_json)
        return self
