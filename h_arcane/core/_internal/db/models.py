"""Database models using SQLModel."""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING

from sqlmodel import SQLModel, Field, Column, Index
from sqlalchemy import JSON
from uuid import UUID, uuid4
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, model_validator

from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.core.status import TaskStatus, TaskTrigger

if TYPE_CHECKING:
    from h_arcane.benchmarks.types import AnyRubric
    from h_arcane.core._internal.task.schema import TaskTreeNode
    from h_arcane.core.runner import ExecutionResult


def _utcnow() -> datetime:
    """Return current UTC time as naive datetime for DB storage."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_uuid_list(data: list[str]) -> list[UUID]:
    """Parse a JSON-stored list of UUID strings."""
    return [UUID(value) for value in data]


# =============================================================================
# Error Tracking Models
# =============================================================================


class ExecutionError(BaseModel):
    """
    Error details for failed tool calls or evaluations.

    Stored as JSON in the `error` column on Action and CriterionResult.
    If error is None, the action/evaluation succeeded.

    No automatic classification - just record what happened, review manually.
    """

    message: str
    exception_type: str | None = None  # e.g., "ModuleNotFoundError"
    stack_trace: str | None = None  # Full traceback for debugging
    details: dict | None = None  # Optional: sandbox logs, extra context


def create_execution_error(
    exception: Exception | None = None,
    message: str | None = None,
    details: dict | None = None,
) -> ExecutionError:
    """
    Create ExecutionError with full stack trace.

    Usage:
        try:
            ...
        except Exception as e:
            error = create_execution_error(e)
    """
    if exception:
        return ExecutionError(
            message=message or str(exception),
            exception_type=type(exception).__name__,
            stack_trace=traceback.format_exc(),
            details=details,
        )
    else:
        return ExecutionError(
            message=message or "Unknown error",
            exception_type=None,
            stack_trace=None,
            details=details,
        )


# =============================================================================
# Core Models
# =============================================================================


class RunStatus(str, Enum):
    """Run execution status."""

    PENDING = "pending"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"


class MessageRole(str, Enum):
    """Message sender role."""

    WORKER = "worker"
    STAKEHOLDER = "stakeholder"


class Experiment(SQLModel, table=True):
    """A task from any supported benchmark."""

    __tablename__ = "experiments"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    # Benchmark identification
    benchmark_name: BenchmarkName = Field(index=True)
    task_id: str = Field(index=True)  # Unique per benchmark_name

    # Task definition
    task_description: str

    # Ground truth evaluation data (rubrics, problem statements, etc.)
    # Structure varies by benchmark_name
    ground_truth_rubric: dict = Field(sa_column=Column(JSON))

    # Benchmark-specific metadata (flexible JSON)
    benchmark_specific_data: dict = Field(default_factory=dict, sa_column=Column(JSON))

    # === NEW: Task tree for DAG-based workflows ===
    # Full DAG structure stored as JSON
    task_tree: dict = Field(default_factory=dict, sa_column=Column(JSON))
    # UUID of the root task (as string)
    root_task_id: str | None = None

    # Generic metadata
    category: str = Field(index=True, default="custom")
    created_at: datetime = Field(default_factory=_utcnow)

    __table_args__ = (
        Index("ix_experiments_benchmark_task", "benchmark_name", "task_id", unique=True),
    )

    def parsed_ground_truth_rubric(self) -> AnyRubric:
        """Parse benchmark-specific ground truth rubric into its typed model."""
        return self.__class__._parse_ground_truth_rubric(
            self.benchmark_name,
            self.ground_truth_rubric,
        )

    @classmethod
    def _parse_ground_truth_rubric(
        cls,
        benchmark_name: BenchmarkName,
        data: dict,
    ) -> AnyRubric:
        """Dispatch rubric parsing based on benchmark name."""
        from h_arcane.core._internal.evaluation.serialization import deserialize_rubric

        rubric_type_by_benchmark = {
            BenchmarkName.GDPEVAL: "StagedRubric",
            BenchmarkName.MINIF2F: "MiniF2FRubric",
            BenchmarkName.RESEARCHRUBRICS: "ResearchRubricsRubric",
            BenchmarkName.SMOKE_TEST: "SmokeTestRubric",
        }
        rubric_type = rubric_type_by_benchmark.get(benchmark_name)
        if rubric_type is None:
            raise ValueError(f"Unsupported benchmark for typed rubric parsing: {benchmark_name}")
        return deserialize_rubric(rubric_type, data)

    def benchmark_specific_data_for(self) -> dict:
        """Return benchmark-specific data without imposing a typed schema yet."""
        return self.__class__._parse_benchmark_specific_data(self.benchmark_specific_data)

    @classmethod
    def _parse_benchmark_specific_data(cls, data: dict) -> dict:
        """Return raw benchmark-specific data for incremental migration."""
        return data or {}

    def parsed_task_tree(self) -> TaskTreeNode | None:
        """Parse the JSON task tree into its typed representation."""
        return self.__class__._parse_task_tree(self.task_tree)

    @classmethod
    def _parse_task_tree(cls, data: dict | None) -> TaskTreeNode | None:
        """Parse stored task tree JSON into a TaskTreeNode."""
        from h_arcane.core._internal.task.schema import parse_task_tree

        return parse_task_tree(data)

    @model_validator(mode="after")
    def validate_task_tree(self) -> Experiment:
        """Fail fast if stored task_tree cannot be parsed."""
        self.__class__._parse_task_tree(self.task_tree)
        return self


class Run(SQLModel, table=True):
    """A single run of an experiment."""

    __tablename__ = "runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    experiment_id: UUID = Field(foreign_key="experiments.id")  # Index defined in __table_args__

    # Worker configuration
    worker_model: str = Field(default="gpt-4o")
    max_questions: int = Field(default=10)

    # Status
    status: RunStatus = Field(default=RunStatus.PENDING)
    error_message: str | None = None

    # E2B sandbox tracking (for cleanup)
    e2b_sandbox_id: str | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=_utcnow)
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None

    # Execution output
    output_text: str | None = None  # Quick text summary/output
    output_resource_ids: list[str] = Field(
        default_factory=list, sa_column=Column(JSON)
    )  # UUIDs of output resources

    # Results (populated on completion)
    final_score: float | None = None
    normalized_score: float | None = None
    questions_asked: int | None = None

    # Cost tracking (denormalized)
    total_cost_usd: float | None = None

    # Benchmark-specific results (flexible JSON)
    benchmark_specific_results: dict = Field(default_factory=dict, sa_column=Column(JSON))

    # Precomputed execution result (set by workflow_complete/workflow_failed)
    # Serialized ExecutionResult - avoids re-querying on completion
    execution_result: dict | None = Field(default=None, sa_column=Column(JSON))

    __table_args__ = (
        Index("ix_runs_experiment", "experiment_id"),
        Index("ix_runs_status", "status"),
    )

    def parsed_output_resource_ids(self) -> list[UUID]:
        """Parse output resource IDs into typed UUIDs."""
        return self.__class__._parse_output_resource_ids(self.output_resource_ids)

    @classmethod
    def _parse_output_resource_ids(cls, data: list[str]) -> list[UUID]:
        """Parse output resource ID strings into UUIDs."""
        return _parse_uuid_list(data)

    def benchmark_specific_results_for(self) -> dict:
        """Return benchmark-specific results without imposing a global schema."""
        return self.__class__._parse_benchmark_specific_results(self.benchmark_specific_results)

    @classmethod
    def _parse_benchmark_specific_results(cls, data: dict) -> dict:
        """Return raw benchmark-specific results for incremental migration."""
        return data or {}

    def cli_request_id(self) -> str | None:
        """Return CLI request ID stored in benchmark-specific results, if present."""
        return self.__class__._parse_cli_request_id(self.benchmark_specific_results_for())

    @classmethod
    def _parse_cli_request_id(cls, data: dict) -> str | None:
        """Extract CLI request ID from benchmark-specific results."""
        value = data.get("cli_request_id")
        if value is None:
            return None
        return str(value)

    def parsed_agent_mapping(self) -> dict[UUID, UUID] | None:
        """Parse persisted worker-to-agent config mapping into UUIDs."""
        return self.__class__._parse_agent_mapping(self.benchmark_specific_results_for())

    @classmethod
    def _parse_agent_mapping(cls, data: dict) -> dict[UUID, UUID] | None:
        """Extract typed agent mapping from benchmark-specific results."""
        mapping = data.get("agent_mapping")
        if mapping is None:
            return None
        if not isinstance(mapping, dict):
            raise ValueError("benchmark_specific_results['agent_mapping'] must be a dict")
        return {UUID(worker_id): UUID(config_id) for worker_id, config_id in mapping.items()}

    def parsed_execution_result(self) -> ExecutionResult | None:
        """Parse precomputed execution result into its typed public API model."""
        return self.__class__._parse_execution_result(self.execution_result)

    @classmethod
    def _parse_execution_result(cls, data: dict | None) -> ExecutionResult | None:
        """Parse stored execution result JSON into ExecutionResult."""
        if data is None:
            return None
        from h_arcane.core.runner import ExecutionResult

        return ExecutionResult.model_validate(data)

    @model_validator(mode="after")
    def validate_execution_result(self) -> Run:
        """Fail fast if stored execution_result cannot be parsed."""
        self.__class__._parse_execution_result(self.execution_result)
        return self


class Message(SQLModel, table=True):
    """A message in the run's conversation history."""

    __tablename__ = "messages"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)

    # Core content
    sender: MessageRole
    content: str
    sequence_num: int  # 0, 1, 2, ...

    # Timing
    created_at: datetime = Field(default_factory=_utcnow)

    # Metadata
    tokens: int | None = None
    cost_usd: float | None = None

    __table_args__ = (Index("ix_messages_run_seq", "run_id", "sequence_num"),)


class Action(SQLModel, table=True):
    """A single action in the worker's execution trace."""

    __tablename__ = "actions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    agent_id: UUID | None = Field(foreign_key="agent_configs.id", index=True, default=None)

    # Ordering
    action_num: int  # 0, 1, 2, ...

    # Action details
    action_type: str  # Tool name: "ask_stakeholder", "read_pdf", etc.
    input: str  # Tool input (JSON or text)
    output: str | None = None  # Tool output

    # Error tracking (None = success)
    error: dict | None = Field(default=None, sa_column=Column(JSON))

    # Timing
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None
    duration_ms: int | None = None

    # Cost (run-level totals at time of action, not per-action)
    agent_total_tokens: int | None = None
    agent_total_cost_usd: float | None = None

    __table_args__ = (
        Index("ix_actions_run_num", "run_id", "action_num"),
        Index("ix_actions_run_type", "run_id", "action_type"),
        Index("ix_actions_agent", "agent_id"),
    )

    @property
    def success(self) -> bool:
        """Convenience: success means no error."""
        return self.error is None

    def parsed_error(self) -> ExecutionError | None:
        """Parse stored error JSON into ExecutionError."""
        return self.__class__._parse_error(self.error)

    @classmethod
    def _parse_error(cls, data: dict | None) -> ExecutionError | None:
        """Parse raw error JSON into ExecutionError."""
        if data is None:
            return None
        return ExecutionError.model_validate(data)

    def get_error(self) -> ExecutionError | None:
        """Get error as ExecutionError object."""
        return self.parsed_error()


class ResourceRecord(SQLModel, table=True):
    """A file resource (input or output) - database record."""

    __tablename__ = "resources"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    # Association: either experiment_id (input) or run_id (output)
    # Indexes defined in __table_args__
    experiment_id: UUID | None = Field(foreign_key="experiments.id", default=None)
    run_id: UUID | None = Field(foreign_key="runs.id", default=None)

    # === NEW: Task-level association for DAG workflows ===
    # Which task this resource belongs to (references task_id in task_tree)
    task_id: UUID | None = Field(default=None)  # Index in __table_args__
    # Which task execution produced this output (for output resources)
    task_execution_id: UUID | None = Field(
        foreign_key="task_executions.id",
        default=None,  # Index in __table_args__
    )
    # True for input resources, False for outputs
    is_input: bool = Field(default=False)

    # File info
    name: str
    mime_type: str
    file_path: str
    size_bytes: int

    # Resource lineage tracking (for output resources)
    source_resource_ids: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="Input resource IDs this output was derived from",
    )

    preview_text: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)

    __table_args__ = (
        Index("ix_resources_experiment", "experiment_id"),
        Index("ix_resources_run", "run_id"),
        Index("ix_resources_task", "task_id"),
        Index("ix_resources_task_execution", "task_execution_id"),
    )

    def load_content(self) -> bytes:
        """Load file content from disk."""
        path = Path(self.file_path)
        if not path.exists():
            raise FileNotFoundError(f"Resource file not found: {path}")
        return path.read_bytes()

    def load_text(self) -> str:
        """Load file content as text."""
        path = Path(self.file_path)
        if not path.exists():
            raise FileNotFoundError(f"Resource file not found: {path}")
        return path.read_text()

    def parsed_source_resource_ids(self) -> list[UUID]:
        """Parse source resource lineage IDs into UUIDs."""
        return self.__class__._parse_source_resource_ids(self.source_resource_ids)

    @classmethod
    def _parse_source_resource_ids(cls, data: list[str]) -> list[UUID]:
        """Parse source resource ID strings into UUIDs."""
        return _parse_uuid_list(data)


class AgentRole(str, Enum):
    """Role of an agent in a workflow."""

    WORKER = "worker"
    STAKEHOLDER = "stakeholder"
    MANAGER = "manager"


class AgentConfig(SQLModel, table=True):
    """Agent configuration snapshot for a run."""

    __tablename__ = "agent_configs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id")  # Index in __table_args__

    # Agent identity
    worker_id: UUID | None = Field(default=None, index=True)  # Original worker UUID from SDK
    name: str  # e.g., "TaskWorker"
    agent_type: str  # e.g., "react_worker"

    # Configuration snapshot
    model: str  # e.g., "gpt-4o"
    system_prompt: str
    tools: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # === NEW: Role in workflow ===
    role: str = Field(default="worker")  # "worker", "stakeholder", "manager"

    created_at: datetime = Field(default_factory=_utcnow)

    __table_args__ = (Index("ix_agent_configs_run", "run_id"),)

    def tool_names(self) -> list[str]:
        """Return persisted tool names."""
        return self.__class__._parse_tools(self.tools)

    @classmethod
    def _parse_tools(cls, data: list[str]) -> list[str]:
        """Return stored tool names as a regular list."""
        return list(data or [])


# =============================================================================
# Task Execution Models (for DAG-based workflows)
# =============================================================================


class TaskExecution(SQLModel, table=True):
    """
    Tracks individual task execution attempts within a run.

    Each task in a DAG workflow can have multiple execution attempts (retries).
    This table records each attempt with its status, timing, and outputs.
    """

    __tablename__ = "task_executions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id")  # Index in __table_args__

    # References task in the task_tree JSON (not a foreign key)
    task_id: UUID = Field()  # Index in __table_args__

    # Which agent executed this task
    agent_id: UUID | None = Field(foreign_key="agent_configs.id", default=None, index=True)

    # Status tracking
    status: TaskStatus = Field(default=TaskStatus.PENDING)  # Index in __table_args__
    attempt_number: int = Field(default=1)

    # Timing
    created_at: datetime = Field(default_factory=_utcnow)
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None

    # Output
    output_text: str | None = None
    output_resource_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Evaluation (if task has evaluator)
    score: float | None = None
    evaluation_details: dict = Field(default_factory=dict, sa_column=Column(JSON))

    # Error tracking
    error_message: str | None = None

    __table_args__ = (
        Index("ix_task_executions_run", "run_id"),
        Index("ix_task_executions_task", "task_id"),
        Index("ix_task_executions_run_task", "run_id", "task_id"),
        Index("ix_task_executions_status", "status"),
    )

    def parsed_output_resource_ids(self) -> list[UUID]:
        """Parse output resource IDs into UUIDs."""
        return self.__class__._parse_output_resource_ids(self.output_resource_ids)

    @classmethod
    def _parse_output_resource_ids(cls, data: list[str]) -> list[UUID]:
        """Parse task execution output resource ID strings into UUIDs."""
        return _parse_uuid_list(data)

    def evaluation_details_for(self) -> dict:
        """Return evaluation details without imposing a stable schema yet."""
        return self.__class__._parse_evaluation_details(self.evaluation_details)

    @classmethod
    def _parse_evaluation_details(cls, data: dict) -> dict:
        """Return raw evaluation details for incremental migration."""
        return data or {}


class TaskStateEvent(SQLModel, table=True):
    """
    Event-sourced log of task state transitions (append-only).

    Each row = one state change. Immutable append-only.
    Enables: replay, audit trail, analytics, "what happened to task X?"

    This is the source of truth for task state history.
    TaskExecution.status is the current state (derived/denormalized).
    """

    __tablename__ = "task_state_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)

    # References task in the task_tree JSON
    task_id: UUID = Field(index=True)

    # Which execution (if any) caused this event
    task_execution_id: UUID | None = Field(
        foreign_key="task_executions.id", index=True, default=None
    )

    # State transition
    event_type: str = (
        Field()
    )  # "status_change", "assigned", "retry", "error" - Index in __table_args__
    old_status: TaskStatus | None = None
    new_status: TaskStatus

    # Context
    triggered_by: TaskTrigger | None = None
    event_metadata: dict = Field(default_factory=dict, sa_column=Column(JSON))

    timestamp: datetime = Field(default_factory=_utcnow)

    __table_args__ = (
        Index("ix_task_state_events_run_task", "run_id", "task_id"),
        Index("ix_task_state_events_timestamp", "timestamp"),
        Index("ix_task_state_events_type", "event_type"),
    )

    def metadata_for(self) -> dict:
        """Return event metadata without imposing an event-type schema yet."""
        return self.__class__._parse_event_metadata(self.event_metadata)

    @classmethod
    def _parse_event_metadata(cls, data: dict) -> dict:
        """Return raw event metadata for incremental migration."""
        return data or {}


class TaskEvaluator(SQLModel, table=True):
    """
    Binds an evaluator (rubric) to a task.

    When a task completes, we query this table to find evaluators to run.
    Supports multiple evaluators per task (e.g., different rubric types).
    """

    __tablename__ = "task_evaluators"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)

    # References task in the task_tree JSON
    task_id: UUID = Field(index=True)

    # Evaluator definition (serialized rubric)
    evaluator_type: str  # "StagedRubric", "MiniF2FRubric", etc.
    evaluator_config: dict = Field(sa_column=Column(JSON))  # Serialized rubric

    # Status tracking
    status: TaskStatus = Field(default=TaskStatus.PENDING)  # Index defined in __table_args__

    # Results (populated after evaluation)
    score: float | None = None
    evaluation_id: UUID | None = Field(foreign_key="evaluations.id", default=None)

    created_at: datetime = Field(default_factory=_utcnow)
    evaluated_at: datetime | None = None

    __table_args__ = (
        Index("ix_task_evaluators_run_task", "run_id", "task_id"),
        Index("ix_task_evaluators_status", "status"),
    )

    def parsed_evaluator(self) -> AnyRubric:
        """Parse stored evaluator config into a live rubric object."""
        return self.__class__._parse_evaluator(self.evaluator_type, self.evaluator_config)

    @classmethod
    def _parse_evaluator(cls, evaluator_type: str, data: dict) -> AnyRubric:
        """Parse evaluator config based on evaluator type."""
        from h_arcane.core._internal.evaluation.serialization import deserialize_rubric

        return deserialize_rubric(evaluator_type, data)

    @model_validator(mode="after")
    def validate_evaluator_config(self) -> TaskEvaluator:
        """Fail fast if stored evaluator config cannot be parsed."""
        self.__class__._parse_evaluator(self.evaluator_type, self.evaluator_config)
        return self


class Evaluation(SQLModel, table=True):
    """Aggregate evaluation result for a run."""

    __tablename__ = "evaluations"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True, unique=True)

    # Aggregate scores
    total_score: float
    max_score: float
    normalized_score: float

    # Stage summary
    stages_evaluated: int
    stages_passed: int
    failed_gate: str | None = None  # First required stage that failed

    evaluated_at: datetime = Field(default_factory=_utcnow)


class CriterionResult(SQLModel, table=True):
    """One row per (run, stage, criterion) — fully queryable."""

    __tablename__ = "criterion_results"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id")  # Index in __table_args__

    # Stage context
    stage_num: int
    stage_name: str

    # Criterion identity
    criterion_num: int  # 0, 1, 2 within stage
    criterion_type: str  # "code_rule" or "llm_judge"
    criterion_description: str

    # Scoring
    score: float
    max_score: float

    # Evaluator reasoning (mandatory)
    feedback: str

    # Full evaluation input (code or prompt)
    evaluation_input: str = Field(
        description="Full execution code (code_rule) or formatted prompt (llm_judge)",
    )

    # Error tracking (None = ran successfully)
    error: dict | None = Field(default=None, sa_column=Column(JSON))

    # What was evaluated — references
    evaluated_action_ids: list[str] = Field(
        default_factory=list, sa_column=Column(JSON)
    )  # UUIDs of actions
    evaluated_resource_ids: list[str] = Field(
        default_factory=list, sa_column=Column(JSON)
    )  # UUIDs of output resources

    __table_args__ = (
        Index("ix_criterion_results_run", "run_id"),
        Index("ix_criterion_results_stage", "stage_name"),
    )

    @property
    def ran_successfully(self) -> bool:
        """Convenience: ran successfully means no error."""
        return self.error is None

    def parsed_error(self) -> ExecutionError | None:
        """Parse stored error JSON into ExecutionError."""
        return self.__class__._parse_error(self.error)

    @classmethod
    def _parse_error(cls, data: dict | None) -> ExecutionError | None:
        """Parse raw error JSON into ExecutionError."""
        if data is None:
            return None
        return ExecutionError.model_validate(data)

    def get_error(self) -> ExecutionError | None:
        """Get error as ExecutionError object."""
        return self.parsed_error()

    def parsed_evaluated_action_ids(self) -> list[UUID]:
        """Parse evaluated action IDs into UUIDs."""
        return self.__class__._parse_evaluated_action_ids(self.evaluated_action_ids)

    @classmethod
    def _parse_evaluated_action_ids(cls, data: list[str]) -> list[UUID]:
        """Parse evaluated action ID strings into UUIDs."""
        return _parse_uuid_list(data)

    def parsed_evaluated_resource_ids(self) -> list[UUID]:
        """Parse evaluated resource IDs into UUIDs."""
        return self.__class__._parse_evaluated_resource_ids(self.evaluated_resource_ids)

    @classmethod
    def _parse_evaluated_resource_ids(cls, data: list[str]) -> list[UUID]:
        """Parse evaluated resource ID strings into UUIDs."""
        return _parse_uuid_list(data)


class TaskEvaluationResult(SQLModel, table=True):
    """Complete task evaluation result snapshot.

    Stores a complete evaluation result including all criterion results and aggregate scores.
    This provides a denormalized view/snapshot of the evaluation state for a run.
    """

    __tablename__ = "task_evaluation_results"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", unique=True)  # Index in __table_args__

    # Criterion results stored as JSON snapshot
    criterion_results: list[dict] = Field(
        default_factory=list, sa_column=Column(JSON)
    )  # List of CriterionResult dicts

    # Aggregate scores
    total_score: float
    max_score: float
    normalized_score: float
    stages_evaluated: int
    stages_passed: int
    failed_gate: str | None = None

    created_at: datetime = Field(default_factory=_utcnow)

    __table_args__ = (Index("ix_task_evaluation_results_run", "run_id"),)

    def parsed_criterion_results(self) -> list[CriterionResult]:
        """Parse stored criterion result snapshots into typed CriterionResult rows."""
        return self.__class__._parse_criterion_results(self.criterion_results)

    @classmethod
    def _parse_criterion_results(cls, data: list[dict]) -> list[CriterionResult]:
        """Parse serialized criterion result snapshots into CriterionResult objects."""
        return [CriterionResult.model_validate(item) for item in data]


# =============================================================================
# Communication Service Models
# =============================================================================


class Thread(SQLModel, table=True):
    """A conversation thread between two agents."""

    __tablename__ = "threads"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    # Context - which run/experiment this thread belongs to
    # Note: indices defined in __table_args__ below, not here (to avoid duplicates)
    run_id: UUID = Field(foreign_key="runs.id")
    experiment_id: UUID = Field(foreign_key="experiments.id")

    # Participants (stored in consistent order for deduplication)
    # Note: composite index defined in __table_args__, individual indices for lookups
    agent_a_id: str = Field(index=True)  # e.g. "{run_id}:worker"
    agent_b_id: str = Field(index=True)  # e.g. "{run_id}:stakeholder"

    # Topic - index defined in __table_args__
    topic: str = Field()

    # Timestamps
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(
        default_factory=_utcnow
    )  # Updated on new message

    __table_args__ = (
        Index("ix_threads_participants", "agent_a_id", "agent_b_id"),
        Index("ix_threads_topic", "topic"),
        Index("ix_threads_run", "run_id"),
        Index("ix_threads_experiment", "experiment_id"),
    )


class ThreadMessage(SQLModel, table=True):
    """A message within a conversation thread."""

    __tablename__ = "thread_messages"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    thread_id: UUID = Field(foreign_key="threads.id", index=True)  # Also in composite index

    # Context - denormalized for query convenience (indexes in __table_args__)
    run_id: UUID = Field(foreign_key="runs.id")
    experiment_id: UUID = Field(foreign_key="experiments.id")

    # Sender/Recipient - indexes in __table_args__
    from_agent_id: str = Field()
    to_agent_id: str = Field()

    # Content
    content: str

    # Ordering and timing
    sequence_num: int  # 0, 1, 2, ... within thread
    created_at: datetime = Field(default_factory=_utcnow)

    __table_args__ = (
        Index("ix_thread_messages_thread_seq", "thread_id", "sequence_num"),
        Index("ix_thread_messages_from", "from_agent_id"),
        Index("ix_thread_messages_to", "to_agent_id"),
        Index("ix_thread_messages_run", "run_id"),
        Index("ix_thread_messages_experiment", "experiment_id"),
    )
