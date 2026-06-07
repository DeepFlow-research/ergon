"""Experiment provenance and candidate-pool tables."""

from datetime import datetime
from uuid import UUID, uuid4

from ergon_core.core.shared.json_types import JsonValue
from ergon_core.core.shared.utils import utcnow as _utcnow
from sqlalchemy import JSON, Boolean, Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel

TZDateTime = DateTime(timezone=True)


class ExperimentRow(SQLModel, table=True):
    __tablename__ = "experiments"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    description: str | None = None
    created_by: str | None = Field(default=None, index=True)
    metadata_json: dict[str, JsonValue] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


class ExperimentEnvironmentRow(SQLModel, table=True):
    __tablename__ = "experiment_environments"
    __table_args__ = (UniqueConstraint("experiment_id", "name"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    experiment_id: UUID = Field(foreign_key="experiments.id", index=True)
    name: str = Field(index=True)
    source_mode: str = Field(index=True)
    source_metadata_json: dict[str, JsonValue] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )
    metadata_json: dict[str, JsonValue] = Field(default_factory=dict, sa_column=Column(JSON))


class ExperimentSamplerInvocationRow(SQLModel, table=True):
    __tablename__ = "experiment_sampler_invocations"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    experiment_id: UUID = Field(foreign_key="experiments.id", index=True)
    sampler_name: str = Field(index=True)
    requested_k: int
    candidate_pool_size: int
    selected_count: int = 0
    policy_version: int | None = Field(default=None, index=True)
    sampler_config_json: dict[str, JsonValue] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


class ExperimentSamplePoolEntryRow(SQLModel, table=True):
    __tablename__ = "experiment_sample_pool_entries"
    __table_args__ = (UniqueConstraint("experiment_id", "environment_id", "sample_key"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    experiment_id: UUID = Field(foreign_key="experiments.id", index=True)
    environment_id: UUID = Field(foreign_key="experiment_environments.id", index=True)
    sampler_invocation_id: UUID | None = Field(
        default=None,
        foreign_key="experiment_sampler_invocations.id",
        index=True,
    )
    sample_key: str = Field(index=True)
    sample_ref_json: dict[str, JsonValue] = Field(default_factory=dict, sa_column=Column(JSON))
    sample_json: dict[str, JsonValue] = Field(default_factory=dict, sa_column=Column(JSON))
    selected: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, default=False, index=True),
    )
    discarded: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, default=False, index=True),
    )
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    selected_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    discarded_at: datetime | None = Field(default=None, sa_type=TZDateTime)
