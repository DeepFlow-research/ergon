"""Reducer and drops-manifest tables for imported/public rollout cards."""

from datetime import datetime
from uuid import UUID, uuid4

from ergon_core.core.shared.json_types import JsonObject
from ergon_core.core.shared.utils import utcnow as _utcnow
from pydantic import model_validator
from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel

TZDateTime = DateTime(timezone=True)


class RunReducer(SQLModel, table=True):
    """Reducer/reporting rule applied to a run."""

    __tablename__ = "run_reducers"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    task_id: UUID | None = Field(default=None, index=True)
    task_execution_id: UUID | None = Field(
        default=None,
        foreign_key="run_task_executions.id",
        index=True,
    )
    name: str = Field(index=True)
    kind: str = Field(index=True)
    implementation_ref: str | None = None
    config_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    input_scope_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    output_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = Field(default="completed", index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

    def parsed_config(self) -> JsonObject:
        return self.__class__._parse_json_object(self.config_json, "config_json")

    def parsed_input_scope(self) -> JsonObject:
        return self.__class__._parse_json_object(self.input_scope_json, "input_scope_json")

    def parsed_output(self) -> JsonObject:
        return self.__class__._parse_json_object(self.output_json, "output_json")

    @classmethod
    def _parse_json_object(cls, data: dict, field_name: str) -> JsonObject:
        if not isinstance(data, dict):
            raise ValueError(f"{field_name} must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_fields(self) -> "RunReducer":
        self.__class__._parse_json_object(self.config_json, "config_json")
        self.__class__._parse_json_object(self.input_scope_json, "input_scope_json")
        self.__class__._parse_json_object(self.output_json, "output_json")
        return self


class RunReducerFootprint(SQLModel, table=True):
    """Compact logical footprint for a reducer."""

    __tablename__ = "run_reducer_footprints"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    reducer_id: UUID = Field(foreign_key="run_reducers.id", index=True)
    source_kind: str = Field(index=True)
    source_id: str | None = None
    namespace: str | None = Field(default=None, index=True)
    fields_read_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    filters_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    aggregation_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    access_kind: str = Field(default="mixed", index=True)
    sequence_min: int | None = None
    sequence_max: int | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

    @model_validator(mode="after")
    def _validate_fields(self) -> "RunReducerFootprint":
        if not isinstance(self.fields_read_json, list):
            raise ValueError("fields_read_json must be a list")
        if not isinstance(self.filters_json, list):
            raise ValueError("filters_json must be a list")
        if not isinstance(self.aggregation_json, dict):
            raise ValueError("aggregation_json must be a dict")
        return self


class RunDropsManifest(SQLModel, table=True):
    """Declared field loss, filtering, or source unavailability for a reducer."""

    __tablename__ = "run_drops_manifests"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    reducer_id: UUID = Field(foreign_key="run_reducers.id", index=True)
    loss_class: str = Field(index=True)
    dropped_source_kind: str | None = None
    dropped_field_path: str | None = Field(default=None, index=True)
    reason: str = Field(index=True)
    affected_analysis: str | None = None
    declaration_kind: str = Field(default="author_declared", index=True)
    evidence_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

    def parsed_evidence(self) -> JsonObject:
        return self.__class__._parse_evidence(self.evidence_json)

    @classmethod
    def _parse_evidence(cls, data: dict) -> JsonObject:
        if not isinstance(data, dict):
            raise ValueError(f"evidence_json must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_fields(self) -> "RunDropsManifest":
        self.__class__._parse_evidence(self.evidence_json)
        return self
