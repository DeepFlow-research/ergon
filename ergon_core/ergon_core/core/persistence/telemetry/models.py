"""Run-scoped telemetry tables.

Telemetry rows reference bound definition rows — they never become the source
of truth for the definition itself.
"""

from datetime import datetime
import sys
from typing import Literal

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):
        pass


from typing import TYPE_CHECKING
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from ergon_core.core.persistence.telemetry.evaluation_summary import (
        EvaluationSummary,
    )

from ergon_core.core.persistence.shared.enums import (
    RunStatus,
    TaskExecutionStatus,
    TrainingStatus,
)
from ergon_core.core.utils import utcnow as _utcnow
from pydantic import model_validator
from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel

TZDateTime = DateTime(timezone=True)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

ExecutionOutcome = Literal["success", "failure"]

# ---------------------------------------------------------------------------
# Cohort status enum
# ---------------------------------------------------------------------------


class ExperimentCohortStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


# ---------------------------------------------------------------------------
# RunRecord
# ---------------------------------------------------------------------------


class RunRecord(SQLModel, table=True):
    __tablename__ = "runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    experiment_definition_id: UUID = Field(
        foreign_key="experiment_definitions.id",
        index=True,
    )
    cohort_id: UUID | None = Field(
        default=None,
        foreign_key="experiment_cohorts.id",
        index=True,
    )
    status: RunStatus = Field(index=True)
    error_message: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    started_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    completed_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    summary_json: dict = Field(default_factory=dict, sa_column=Column(JSON))

    # -- JSON accessor: summary_json --

    def parsed_summary(self) -> dict[str, object]:
        return self.__class__._parse_summary(self.summary_json)

    @classmethod
    def _parse_summary(cls, data: dict) -> dict[str, object]:
        if not isinstance(data, dict):
            raise ValueError(f"summary_json must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_summary_json(self) -> "RunRecord":
        self.__class__._parse_summary(self.summary_json)
        return self


# ---------------------------------------------------------------------------
# RunTaskExecution
# ---------------------------------------------------------------------------


class RunTaskExecution(SQLModel, table=True):
    __tablename__ = "run_task_executions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    definition_task_id: UUID = Field(
        foreign_key="experiment_definition_tasks.id",
        index=True,
    )
    definition_worker_id: UUID | None = Field(
        default=None,
        foreign_key="experiment_definition_workers.id",
        index=True,
    )
    attempt_number: int = 1
    status: TaskExecutionStatus = Field(index=True)
    started_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    completed_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    output_text: str | None = None
    output_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    error_json: dict | None = Field(default=None, sa_column=Column(JSON))

    # -- JSON accessor: output_json --

    def parsed_output(self) -> dict[str, object]:
        return self.__class__._parse_output(self.output_json)

    @classmethod
    def _parse_output(cls, data: dict) -> dict[str, object]:
        if not isinstance(data, dict):
            raise ValueError(f"output_json must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_output_json(self) -> "RunTaskExecution":
        self.__class__._parse_output(self.output_json)
        return self

    # -- JSON accessor: error_json (nullable) --

    def parsed_error(self) -> dict[str, object] | None:
        return self.__class__._parse_error(self.error_json)

    @classmethod
    def _parse_error(cls, data: dict | None) -> dict[str, object] | None:
        if data is None:
            return None
        if not isinstance(data, dict):
            raise ValueError(f"error_json must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_error_json(self) -> "RunTaskExecution":
        self.__class__._parse_error(self.error_json)
        return self


# ---------------------------------------------------------------------------
# RunAction
# ---------------------------------------------------------------------------


class RunAction(SQLModel, table=True):
    __tablename__ = "run_actions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    task_execution_id: UUID = Field(
        foreign_key="run_task_executions.id",
        index=True,
    )
    action_num: int
    action_type: str
    input_text: str
    output_text: str | None = None
    error_json: dict | None = Field(default=None, sa_column=Column(JSON))
    started_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    completed_at: datetime | None = Field(default=None, sa_type=TZDateTime)

    # -- JSON accessor: error_json (nullable) --

    def parsed_error(self) -> dict[str, object] | None:
        return self.__class__._parse_error(self.error_json)

    @classmethod
    def _parse_error(cls, data: dict | None) -> dict[str, object] | None:
        if data is None:
            return None
        if not isinstance(data, dict):
            raise ValueError(f"error_json must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_error_json(self) -> "RunAction":
        self.__class__._parse_error(self.error_json)
        return self


# ---------------------------------------------------------------------------
# RunResource
# ---------------------------------------------------------------------------


class RunResource(SQLModel, table=True):
    __tablename__ = "run_resources"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    task_execution_id: UUID | None = Field(
        default=None,
        foreign_key="run_task_executions.id",
    )
    kind: Literal["output"] = "output"
    name: str
    mime_type: str
    file_path: str
    size_bytes: int
    metadata_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

    # -- JSON accessor: metadata_json --

    def parsed_metadata(self) -> dict[str, object]:
        return self.__class__._parse_metadata(self.metadata_json)

    @classmethod
    def _parse_metadata(cls, data: dict) -> dict[str, object]:
        if not isinstance(data, dict):
            raise ValueError(f"metadata_json must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_metadata_json(self) -> "RunResource":
        self.__class__._parse_metadata(self.metadata_json)
        return self


# ---------------------------------------------------------------------------
# RunTaskStateEvent
# ---------------------------------------------------------------------------


class RunTaskStateEvent(SQLModel, table=True):
    __tablename__ = "run_task_state_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    definition_task_id: UUID = Field(
        foreign_key="experiment_definition_tasks.id",
        index=True,
    )
    task_execution_id: UUID | None = Field(
        default=None,
        foreign_key="run_task_executions.id",
    )
    event_type: Literal["state_change"] = Field(default="state_change", index=True)
    old_status: TaskExecutionStatus | None = None
    new_status: TaskExecutionStatus
    event_metadata: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

    # -- JSON accessor: event_metadata --

    def parsed_event_metadata(self) -> dict[str, object]:
        return self.__class__._parse_event_metadata(self.event_metadata)

    @classmethod
    def _parse_event_metadata(cls, data: dict) -> dict[str, object]:
        if not isinstance(data, dict):
            raise ValueError(f"event_metadata must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_event_metadata(self) -> "RunTaskStateEvent":
        self.__class__._parse_event_metadata(self.event_metadata)
        return self


# ---------------------------------------------------------------------------
# RunTaskEvaluation
# ---------------------------------------------------------------------------


class RunTaskEvaluation(SQLModel, table=True):
    __tablename__ = "run_task_evaluations"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    definition_task_id: UUID = Field(
        foreign_key="experiment_definition_tasks.id",
        index=True,
    )
    definition_evaluator_id: UUID = Field(
        foreign_key="experiment_definition_evaluators.id",
        index=True,
    )
    score: float | None = None
    passed: bool | None = None
    feedback: str | None = None
    summary_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

    # -- JSON accessor: summary_json --

    def parsed_summary(self) -> "EvaluationSummary":
        # Deferred: avoid circular import
        from ergon_core.core.persistence.telemetry.evaluation_summary import (
            EvaluationSummary,
        )

        return EvaluationSummary.model_validate(self.summary_json)

    @model_validator(mode="after")
    def _validate_summary_json(self) -> "RunTaskEvaluation":
        if not isinstance(self.summary_json, dict):
            raise ValueError(f"summary_json must be a dict, got {type(self.summary_json).__name__}")
        return self


# ---------------------------------------------------------------------------
# ExperimentCohort
# ---------------------------------------------------------------------------


class ExperimentCohort(SQLModel, table=True):
    """A named grouping of runs that the operator monitors as one unit."""

    __tablename__ = "experiment_cohorts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True, unique=True)
    description: str | None = None
    created_by: str | None = None
    status: ExperimentCohortStatus = Field(default=ExperimentCohortStatus.ACTIVE)
    metadata_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

    # -- JSON accessor: metadata_json --

    def parsed_metadata(self) -> dict[str, object]:
        return self.__class__._parse_metadata(self.metadata_json)

    @classmethod
    def _parse_metadata(cls, data: dict) -> dict[str, object]:
        if not isinstance(data, dict):
            raise ValueError(f"metadata_json must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_metadata_json(self) -> "ExperimentCohort":
        self.__class__._parse_metadata(self.metadata_json)
        return self


# ---------------------------------------------------------------------------
# ExperimentCohortStats
# ---------------------------------------------------------------------------


class ExperimentCohortStats(SQLModel, table=True):
    """Denormalized aggregate snapshot for a cohort."""

    __tablename__ = "experiment_cohort_stats"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    cohort_id: UUID = Field(foreign_key="experiment_cohorts.id", index=True, unique=True)
    total_runs: int = 0
    completed_runs: int = 0
    failed_runs: int = 0
    average_score: float | None = None
    best_score: float | None = None
    worst_score: float | None = None
    average_duration_ms: int | None = None
    failure_rate: float = 0.0
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


# ---------------------------------------------------------------------------
# Thread (inter-agent communication)
# ---------------------------------------------------------------------------


class Thread(SQLModel, table=True):
    __tablename__ = "threads"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    topic: str
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
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    task_execution_id: UUID | None = Field(
        default=None,
        foreign_key="run_task_executions.id",
        index=True,
    )
    from_agent_id: str
    to_agent_id: str
    content: str
    sequence_num: int
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


# ---------------------------------------------------------------------------
# RunGenerationTurn — lossless per-turn generation record
# ---------------------------------------------------------------------------


class RunGenerationTurn(SQLModel, table=True):
    """Lossless per-turn record of one model generation within an episode.

    Stores the exact provider exchange (raw_request/raw_response) plus
    convenience extractions and optional RL fields.  One row per model
    call per task execution.  Persisted incrementally — one commit per
    yield from the worker's async generator.
    """

    __tablename__ = "run_generation_turns"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    task_execution_id: UUID = Field(
        foreign_key="run_task_executions.id",
        index=True,
    )
    worker_binding_key: str = Field(index=True)
    turn_index: int

    # Lossless provider exchange
    raw_request: dict = Field(default_factory=dict, sa_column=Column(JSON))
    raw_response: dict = Field(default_factory=dict, sa_column=Column(JSON))

    # Convenience extractions
    response_text: str | None = None
    tool_calls_json: list[dict[str, object]] | None = Field(default=None, sa_column=Column(JSON))
    tool_results_json: list[dict[str, object]] | None = Field(default=None, sa_column=Column(JSON))

    # RL fields (None for cloud APIs, populated for vLLM)
    token_ids_json: list[int] | None = Field(default=None, sa_column=Column(JSON))
    logprobs_json: list[dict[str, object]] | None = Field(default=None, sa_column=Column(JSON))
    policy_version: str | None = None

    # Execution outcome at time of persist
    execution_outcome: ExecutionOutcome | None = Field(default=None, index=True)

    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

    # -- JSON accessors --

    def parsed_tool_calls(self) -> list[dict[str, object]]:
        return self._parse_optional_list("tool_calls_json", self.tool_calls_json) or []

    def parsed_tool_results(self) -> list[dict[str, object]]:
        return self._parse_optional_list("tool_results_json", self.tool_results_json) or []

    def parsed_token_ids(self) -> list[int] | None:
        return self._parse_optional_list("token_ids_json", self.token_ids_json)

    def parsed_logprobs(self) -> list[dict[str, object]] | None:
        return self._parse_optional_list("logprobs_json", self.logprobs_json)

    # -- shared helpers --

    @classmethod
    def _parse_optional_list(cls, field_name: str, data: list | None) -> list | None:
        if data is None:
            return None
        if not isinstance(data, list):
            raise ValueError(f"{field_name} must be a list, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_json_columns(self) -> "RunGenerationTurn":
        if not isinstance(self.raw_request, dict):
            raise ValueError(f"raw_request must be a dict, got {type(self.raw_request).__name__}")
        if not isinstance(self.raw_response, dict):
            raise ValueError(f"raw_response must be a dict, got {type(self.raw_response).__name__}")
        return self


# ---------------------------------------------------------------------------
# TrainingSession — tracks an RL training run
# ---------------------------------------------------------------------------


class TrainingSession(SQLModel, table=True):
    """One invocation of ``ergon train`` (local or launched).

    Links a training run to the ExperimentDefinition it trains against,
    stores the training config, and anchors per-step metrics.
    """

    __tablename__ = "training_sessions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    experiment_definition_id: UUID = Field(
        foreign_key="experiment_definitions.id",
        index=True,
    )
    model_name: str
    config_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    status: TrainingStatus = Field(default=TrainingStatus.RUNNING, index=True)
    started_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    completed_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    output_dir: str | None = None
    total_steps: int | None = None
    final_loss: float | None = None


# ---------------------------------------------------------------------------
# TrainingMetric — per-step training metrics
# ---------------------------------------------------------------------------


class TrainingMetric(SQLModel, table=True):
    """One row per logged training step.

    Written by ``ErgonTrainingCallback.on_log()`` during training.
    """

    __tablename__ = "training_metrics"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    session_id: UUID = Field(foreign_key="training_sessions.id", index=True)
    step: int
    epoch: float | None = None
    loss: float | None = None
    grad_norm: float | None = None
    learning_rate: float | None = None
    reward_mean: float | None = None
    reward_std: float | None = None
    entropy: float | None = None
    completion_mean_length: float | None = None
    step_time_s: float | None = None
    extra_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
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
    definition_id: UUID = Field(foreign_key="experiment_definitions.id", index=True)
    status: str = Field(default="pending", index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


class RolloutBatchRun(SQLModel, table=True):
    """Join table: which runs belong to which batch."""

    __tablename__ = "rollout_batch_runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    batch_id: UUID = Field(foreign_key="rollout_batches.id", index=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
