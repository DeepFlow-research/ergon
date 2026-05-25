"""Run-scoped telemetry tables.

Telemetry rows reference bound definition rows — they never become the source
of truth for the definition itself.
"""

from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from ergon_core.core.shared.json_types import JsonObject
from ergon_core.core.persistence.shared.enums import (
    SampleStatus,
    TaskExecutionStatus,
)
from ergon_core.core.shared.rollout_status import RolloutStatus
from ergon_core.core.shared.utils import utcnow as _utcnow
from pydantic import model_validator
from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel

TZDateTime = DateTime(timezone=True)

# model_validator(mode="after") fires on model_validate() but NOT on direct
# SQLModel table model construction (SQLModel's __init__ bypasses Pydantic
# for table=True). Validators here protect the API/deserialization boundary.

# ---------------------------------------------------------------------------
# SampleRecord
# ---------------------------------------------------------------------------


class SampleRecord(SQLModel, table=True):
    __tablename__ = "samples"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    definition_id: UUID = Field(
        foreign_key="experiment_definitions.id",
        index=True,
        description="Canonical runtime ExperimentDefinition id for this run.",
    )
    benchmark_type: str = Field(index=True)
    instance_key: str = Field(index=True)
    sample_id: str | None = Field(default=None, index=True)
    worker_team_json: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON),
        description=(
            "Compatibility/display-only worker selection snapshot; runtime "
            "execution uses object-bound task snapshots."
        ),
    )
    evaluator_slug: str | None = Field(
        default=None,
        index=True,
        description=(
            "Compatibility/display-only evaluator slug; runtime evaluation "
            "uses object-bound task snapshots and definition evaluator rows."
        ),
    )
    model_target: str | None = None
    sandbox_slug: str | None = Field(
        default=None,
        index=True,
        description=(
            "Compatibility/display-only sandbox slug; runtime sandbox setup "
            "is moving to object-bound task snapshots."
        ),
    )
    dependency_extras_json: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON),
        description=(
            "Compatibility/display-only dependency extras snapshot retained for older run displays."
        ),
    )
    assignment_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    seed: int | None = None
    experiment: str | None = Field(
        default=None,
        index=True,
        description=(
            "Optional v2 experiment grouping tag for runs. This is a label "
            "for grouping related runs, not a foreign key to a retired table."
        ),
    )
    status: SampleStatus = Field(index=True)
    error_message: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    started_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    completed_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    summary_json: dict = Field(default_factory=dict, sa_column=Column(JSON))

    def parsed_worker_team(self) -> JsonObject:
        return self.__class__._parse_json_object(self.worker_team_json, "worker_team_json")

    def parsed_assignment(self) -> JsonObject:
        return self.__class__._parse_json_object(self.assignment_json, "assignment_json")

    def parsed_dependency_extras(self) -> JsonObject:
        return self.__class__._parse_json_object(
            self.dependency_extras_json, "dependency_extras_json"
        )

    def parsed_summary(self) -> JsonObject:
        return self.__class__._parse_json_object(self.summary_json, "summary_json")

    @classmethod
    def _parse_json_object(cls, data: dict, field_name: str) -> JsonObject:
        if not isinstance(data, dict):
            raise ValueError(f"{field_name} must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_fields(self) -> "SampleRecord":
        self.__class__._parse_json_object(self.worker_team_json, "worker_team_json")
        self.__class__._parse_json_object(self.dependency_extras_json, "dependency_extras_json")
        self.__class__._parse_json_object(self.assignment_json, "assignment_json")
        self.__class__._parse_json_object(self.summary_json, "summary_json")
        try:
            SampleStatus(self.status)
        except ValueError:
            raise ValueError(
                f"{self.status!r} is not a valid SampleStatus; "
                f"valid values: {[e.value for e in SampleStatus]}"
            )
        return self


# ---------------------------------------------------------------------------
# SampleTaskAttempt
# ---------------------------------------------------------------------------


class SampleTaskAttempt(SQLModel, table=True):
    __tablename__ = "sample_task_attempts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sample_id: UUID = Field(foreign_key="samples.id", index=True)
    task_id: UUID = Field(index=True)
    definition_worker_id: UUID | None = Field(
        default=None,
        foreign_key="experiment_definition_workers.id",
        index=True,
    )
    attempt_number: int = 1
    status: TaskExecutionStatus = Field(index=True)
    started_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    completed_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    final_assistant_message: str | None = None
    output_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    error_json: dict | None = Field(default=None, sa_column=Column(JSON))
    sandbox_id: str | None = None
    # TODO(post-stack): relocate this column behind a lazy
    # `await context.worker_output()` accessor on `CriterionContext`.
    # Today the runtime pre-loads worker output in `evaluate_task_run` and
    # stuffs it onto `worker_result`, but every other context capability
    # (`run_command`, `read_resource`, ...) is fetched lazily by the
    # criterion. When that redesign lands, this column may live in a
    # dedicated output store rather than on `SampleTaskAttempt`.
    worker_output_json: dict | None = Field(default=None, sa_column=Column(JSON))

    # -- JSON accessor: output_json --

    def parsed_output(self) -> JsonObject:
        return self.__class__._parse_output(self.output_json)

    @classmethod
    def _parse_output(cls, data: dict) -> JsonObject:
        if not isinstance(data, dict):
            raise ValueError(f"output_json must be a dict, got {type(data).__name__}")
        return data

    # -- JSON accessor: error_json (nullable) --

    def parsed_error(self) -> JsonObject | None:
        return self.__class__._parse_error(self.error_json)

    @classmethod
    def _parse_error(cls, data: dict | None) -> JsonObject | None:
        if data is None:
            return None
        if not isinstance(data, dict):
            raise ValueError(f"error_json must be a dict, got {type(data).__name__}")
        return data

    def validate_identity(self) -> None:
        """Require enough identity to map execution rows to a static or dynamic task."""
        if self.task_id is None:
            raise ValueError("SampleTaskAttempt requires task_id")

    @model_validator(mode="after")
    def _validate_fields(self) -> "SampleTaskAttempt":
        self.__class__._parse_output(self.output_json)
        self.__class__._parse_error(self.error_json)
        self.validate_identity()
        try:
            TaskExecutionStatus(self.status)
        except ValueError:
            raise ValueError(
                f"{self.status!r} is not a valid TaskExecutionStatus; "
                f"valid values: {[e.value for e in TaskExecutionStatus]}"
            )
        return self


# ---------------------------------------------------------------------------
# SampleResource
# ---------------------------------------------------------------------------


class SampleResource(SQLModel, table=True):
    __tablename__ = "sample_resources"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sample_id: UUID = Field(foreign_key="samples.id", index=True)
    task_execution_id: UUID | None = Field(
        default=None,
        foreign_key="sample_task_attempts.id",
    )
    kind: str = Field(
        default="output",
        description="Canonical artifact kind from shared SampleResourceKind.",
    )
    name: str
    mime_type: str
    file_path: str
    size_bytes: int
    metadata_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

    # Append-only log support
    error: str | None = Field(default=None)
    content_hash: str | None = Field(default=None, index=True)
    copied_from_resource_id: UUID | None = Field(
        default=None,
        foreign_key="sample_resources.id",
        index=True,
    )

    # -- JSON accessor: metadata_json --

    def parsed_metadata(self) -> JsonObject:
        return self.__class__._parse_metadata(self.metadata_json)

    @classmethod
    def _parse_metadata(cls, data: dict) -> JsonObject:
        if not isinstance(data, dict):
            raise ValueError(f"metadata_json must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_fields(self) -> "SampleResource":
        from ergon_core.core.persistence.shared.enums import SampleResourceKind

        self.__class__._parse_metadata(self.metadata_json)
        try:
            SampleResourceKind(self.kind)
        except ValueError:
            raise ValueError(
                f"{self.kind!r} is not a valid SampleResourceKind; "
                f"valid values: {[e.value for e in SampleResourceKind]}"
            )
        return self


# ---------------------------------------------------------------------------
# SampleTaskEvaluation
# ---------------------------------------------------------------------------


class SampleTaskEvaluation(SQLModel, table=True):
    __tablename__ = "sample_task_evaluations"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sample_id: UUID = Field(foreign_key="samples.id", index=True)
    task_execution_id: UUID = Field(
        foreign_key="sample_task_attempts.id",
        index=True,
    )
    task_id: UUID = Field(index=True)
    definition_evaluator_id: UUID = Field(
        foreign_key="experiment_definition_evaluators.id",
        index=True,
    )
    score: float | None = None
    passed: bool | None = None
    feedback: str | None = None
    summary_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

    @model_validator(mode="after")
    def _validate_summary_json(self) -> "SampleTaskEvaluation":
        if not isinstance(self.summary_json, dict):
            raise ValueError(f"summary_json must be a dict, got {type(self.summary_json).__name__}")
        return self


# ---------------------------------------------------------------------------
# Thread (inter-agent communication)
# ---------------------------------------------------------------------------


class Thread(SQLModel, table=True):
    __tablename__ = "threads"
    __table_args__ = (sa.UniqueConstraint("sample_id", "topic", name="uq_threads_run_topic"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sample_id: UUID = Field(foreign_key="samples.id", index=True)
    topic: str
    summary: str | None = None
    agent_a_id: str = Field(index=True)
    agent_b_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


# ---------------------------------------------------------------------------
# ThreadMessage
# ---------------------------------------------------------------------------


class ThreadMessage(SQLModel, table=True):
    __tablename__ = "thread_messages"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    thread_id: UUID = Field(foreign_key="threads.id", index=True)
    sample_id: UUID = Field(foreign_key="samples.id", index=True)
    task_execution_id: UUID | None = Field(
        default=None,
        foreign_key="sample_task_attempts.id",
        index=True,
    )
    from_agent_id: str
    to_agent_id: str
    content: str
    sequence_num: int
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


# ---------------------------------------------------------------------------
# RolloutBatch — durable batch state for the rollout service
# ---------------------------------------------------------------------------


class RolloutBatch(SQLModel, table=True):
    """One rollout batch submitted by the RL trainer.

    Replaces the in-memory ``_batches`` dict on ``RolloutService``.
    Survives API restarts — the trainer can reconnect and poll.
    """

    __tablename__ = "rollout_batches"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    definition_id: UUID | None = Field(
        default=None,
        foreign_key="experiment_definitions.id",
        index=True,
    )
    sampler_invocation_id: UUID | None = Field(default=None, index=True)
    status: RolloutStatus = Field(default=RolloutStatus.PENDING, index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

    @model_validator(mode="after")
    def _validate_fields(self) -> "RolloutBatch":
        try:
            RolloutStatus(self.status)
        except ValueError:
            raise ValueError(
                f"{self.status!r} is not a valid RolloutBatch status; "
                f"valid values: {[e.value for e in RolloutStatus]}"
            )
        return self


class RolloutBatchSampleMembership(SQLModel, table=True):
    """Join table: which samples belong to which rollout batch."""

    __tablename__ = "rollout_batch_sample_memberships"

    batch_id: UUID = Field(foreign_key="rollout_batches.id", primary_key=True)
    sample_id: UUID = Field(foreign_key="samples.id", primary_key=True)
    environment_id: UUID | None = Field(default=None, index=True)
    pool_entry_id: UUID | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


# ---------------------------------------------------------------------------
# SandboxCommandWalEntry — append-only log of bash commands run in a sandbox
# ---------------------------------------------------------------------------


class SandboxCommandWalEntry(SQLModel, table=True):
    """One row per bash command emitted by ``SandboxEventSink.sandbox_command``.

    ``sample_id`` is indexed but carries no FK constraint — the sandbox.closed
    synthetic WAL entry may arrive with sample_id=task_id due to a pre-existing
    quirk in the manager's teardown sequence.  Queries should filter by
    sample_id; rows with an unexpected sample_id will simply not appear.
    """

    __tablename__ = "sandbox_command_wal_entries"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sample_id: UUID = Field(index=True)
    task_id: UUID = Field(index=True)
    sandbox_id: str = Field(index=True)
    command: str
    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None
    duration_ms: int | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


# ---------------------------------------------------------------------------
# SandboxEvent — sandbox_created / sandbox_closed lifecycle events
# ---------------------------------------------------------------------------


class SandboxEvent(SQLModel, table=True):
    """One row per sandbox lifecycle event emitted by ``SandboxEventSink``.

    ``kind`` is one of ``"sandbox_created"`` or ``"sandbox_closed"``.
    ``sample_id`` carries no FK — same teardown-sequence caveat as
    ``SandboxCommandWalEntry``.
    """

    __tablename__ = "sandbox_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sample_id: UUID = Field(index=True)
    task_id: UUID = Field(index=True)
    sandbox_id: str = Field(index=True)
    kind: str
    timeout_minutes: int | None = None
    template: str | None = None
    reason: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
