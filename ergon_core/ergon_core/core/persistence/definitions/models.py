"""Immutable experiment-definition tables.

These store identity (type slugs, model targets, binding keys) not serialized
Python constructor state.  The runtime reconstructs live objects from the
registry using these identity fields.
"""

from datetime import datetime
from typing import TypeVar
from uuid import UUID, uuid4

from ergon_core.api.json_types import JsonObject
from ergon_core.core.utils import utcnow as _utcnow
from pydantic import BaseModel, model_validator
from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel

TZDateTime = DateTime(timezone=True)
PayloadModelT = TypeVar("PayloadModelT", bound=BaseModel)

# ---------------------------------------------------------------------------
# ExperimentDefinition
# ---------------------------------------------------------------------------


class ExperimentDefinition(SQLModel, table=True):
    __tablename__ = "experiment_definitions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    benchmark_type: str = Field(index=True)
    metadata_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

    # JSON accessor pattern: parsed_*() returns typed model, _parse_*()
    # classmethod for reuse, @model_validator for fail-fast at row load.
    # Core code never reads raw dict from a JSON column.

    def parsed_metadata(self) -> JsonObject:
        return self.__class__._parse_metadata(self.metadata_json)

    @classmethod
    def _parse_metadata(cls, data: dict) -> JsonObject:
        if not isinstance(data, dict):
            raise ValueError(f"metadata_json must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_metadata_json(self) -> "ExperimentDefinition":
        self.__class__._parse_metadata(self.metadata_json)
        return self


# ---------------------------------------------------------------------------
# ExperimentDefinitionWorker
# ---------------------------------------------------------------------------


class ExperimentDefinitionWorker(SQLModel, table=True):
    __tablename__ = "experiment_definition_workers"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    experiment_definition_id: UUID = Field(
        foreign_key="experiment_definitions.id",
        index=True,
    )
    binding_key: str = Field(index=True)
    worker_type: str = Field(index=True)
    model_target: str
    snapshot_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

    # -- JSON accessor: snapshot_json --

    def parsed_snapshot(self) -> JsonObject:
        return self.__class__._parse_snapshot(self.snapshot_json)

    @classmethod
    def _parse_snapshot(cls, data: dict) -> JsonObject:
        if not isinstance(data, dict):
            raise ValueError(f"snapshot_json must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_snapshot_json(self) -> "ExperimentDefinitionWorker":
        self.__class__._parse_snapshot(self.snapshot_json)
        return self


# ---------------------------------------------------------------------------
# ExperimentDefinitionEvaluator
# ---------------------------------------------------------------------------


class ExperimentDefinitionEvaluator(SQLModel, table=True):
    __tablename__ = "experiment_definition_evaluators"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    experiment_definition_id: UUID = Field(
        foreign_key="experiment_definitions.id",
        index=True,
    )
    binding_key: str = Field(index=True)
    evaluator_type: str = Field(index=True)
    snapshot_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

    # -- JSON accessor: snapshot_json --

    def parsed_snapshot(self) -> JsonObject:
        return self.__class__._parse_snapshot(self.snapshot_json)

    @classmethod
    def _parse_snapshot(cls, data: dict) -> JsonObject:
        if not isinstance(data, dict):
            raise ValueError(f"snapshot_json must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_snapshot_json(self) -> "ExperimentDefinitionEvaluator":
        self.__class__._parse_snapshot(self.snapshot_json)
        return self


# ---------------------------------------------------------------------------
# ExperimentDefinitionInstance
# ---------------------------------------------------------------------------


class ExperimentDefinitionInstance(SQLModel, table=True):
    __tablename__ = "experiment_definition_instances"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    experiment_definition_id: UUID = Field(
        foreign_key="experiment_definitions.id",
        index=True,
    )
    instance_key: str = Field(index=True)
    benchmark_instance_state: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

    # -- JSON accessor: benchmark_instance_state --

    def parsed_instance_state(self) -> JsonObject:
        return self.__class__._parse_instance_state(self.benchmark_instance_state)

    @classmethod
    def _parse_instance_state(cls, data: dict) -> JsonObject:
        if not isinstance(data, dict):
            raise ValueError(f"benchmark_instance_state must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_benchmark_instance_state(self) -> "ExperimentDefinitionInstance":
        self.__class__._parse_instance_state(self.benchmark_instance_state)
        return self


# ---------------------------------------------------------------------------
# ExperimentDefinitionTask
# ---------------------------------------------------------------------------


class ExperimentDefinitionTask(SQLModel, table=True):
    __tablename__ = "experiment_definition_tasks"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    experiment_definition_id: UUID = Field(
        foreign_key="experiment_definitions.id",
        index=True,
    )
    instance_id: UUID = Field(
        foreign_key="experiment_definition_instances.id",
        index=True,
    )
    task_slug: str = Field(index=True)
    parent_task_id: UUID | None = Field(
        default=None,
        foreign_key="experiment_definition_tasks.id",
    )
    task_type: str | None = None
    description: str
    task_payload_json: JsonObject = Field(
        default_factory=dict,
        sa_column=Column("task_payload", JSON),
    )
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

    # -- JSON accessor: task_payload --

    def task_payload_as(self, payload_model: type[PayloadModelT]) -> PayloadModelT:
        return payload_model.model_validate(self.task_payload_json)

    @classmethod
    def _parse_task_payload_json(cls, data: JsonObject) -> JsonObject:
        if not isinstance(data, dict):
            raise ValueError(f"task_payload_json must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_task_payload(self) -> "ExperimentDefinitionTask":
        self.__class__._parse_task_payload_json(self.task_payload_json)
        return self


# ---------------------------------------------------------------------------
# ExperimentDefinitionTaskDependency
# ---------------------------------------------------------------------------


class ExperimentDefinitionTaskDependency(SQLModel, table=True):
    __tablename__ = "experiment_definition_task_dependencies"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    experiment_definition_id: UUID = Field(
        foreign_key="experiment_definitions.id",
        index=True,
    )
    task_id: UUID = Field(
        foreign_key="experiment_definition_tasks.id",
        index=True,
    )
    depends_on_task_id: UUID = Field(
        foreign_key="experiment_definition_tasks.id",
        index=True,
    )
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


# ---------------------------------------------------------------------------
# ExperimentDefinitionTaskAssignment
# ---------------------------------------------------------------------------


class ExperimentDefinitionTaskAssignment(SQLModel, table=True):
    __tablename__ = "experiment_definition_task_assignments"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    experiment_definition_id: UUID = Field(
        foreign_key="experiment_definitions.id",
        index=True,
    )
    task_id: UUID = Field(
        foreign_key="experiment_definition_tasks.id",
        index=True,
    )
    worker_binding_key: str = Field(index=True)
    assignment_type: str = Field(default="initial")
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


# ---------------------------------------------------------------------------
# ExperimentDefinitionTaskEvaluator
# ---------------------------------------------------------------------------


class ExperimentDefinitionTaskEvaluator(SQLModel, table=True):
    __tablename__ = "experiment_definition_task_evaluators"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    experiment_definition_id: UUID = Field(
        foreign_key="experiment_definitions.id",
        index=True,
    )
    task_id: UUID = Field(
        foreign_key="experiment_definition_tasks.id",
        index=True,
    )
    evaluator_binding_key: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
