"""Database models using SQLModel."""

from sqlmodel import SQLModel, Field, Column, Index
from sqlalchemy import JSON
from uuid import UUID, uuid4
from datetime import datetime
from enum import Enum
from pathlib import Path

from h_arcane.core.models.enums import BenchmarkName


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

    __tablename__ = "experiments"  # type: ignore[assignment]

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

    # Generic metadata
    category: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index("ix_experiments_benchmark_task", "benchmark_name", "task_id", unique=True),
    )


class Run(SQLModel, table=True):
    """A single run of an experiment."""

    __tablename__ = "runs"  # type: ignore[assignment]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    experiment_id: UUID = Field(foreign_key="experiments.id", index=True)

    # Worker configuration
    worker_model: str = Field(default="gpt-4o")
    max_questions: int = Field(default=10)

    # Status
    status: RunStatus = Field(default=RunStatus.PENDING)
    error_message: str | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
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

    __table_args__ = (
        Index("ix_runs_experiment", "experiment_id"),
        Index("ix_runs_status", "status"),
    )


class Message(SQLModel, table=True):
    """A message in the run's conversation history."""

    __tablename__ = "messages"  # type: ignore[assignment]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)

    # Core content
    sender: MessageRole
    content: str
    sequence_num: int  # 0, 1, 2, ...

    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Metadata
    tokens: int | None = None
    cost_usd: float | None = None

    __table_args__ = (Index("ix_messages_run_seq", "run_id", "sequence_num"),)


class Action(SQLModel, table=True):
    """A single action in the worker's execution trace."""

    __tablename__ = "actions"  # type: ignore[assignment]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    agent_id: UUID | None = Field(foreign_key="agent_configs.id", index=True, default=None)

    # Ordering
    action_num: int  # 0, 1, 2, ...

    # Action details
    action_type: str  # Tool name: "ask_stakeholder", "read_pdf", etc.
    input: str  # Tool input (JSON or text)
    output: str | None = None  # Tool output

    # Timing
    started_at: datetime = Field(default_factory=datetime.utcnow)
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


class Resource(SQLModel, table=True):
    """A file resource (input or output)."""

    __tablename__ = "resources"  # type: ignore[assignment]

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    # Association: either experiment_id (input) or run_id (output)
    experiment_id: UUID | None = Field(foreign_key="experiments.id", index=True, default=None)
    run_id: UUID | None = Field(foreign_key="runs.id", index=True, default=None)

    # File info
    name: str
    mime_type: str
    file_path: str
    size_bytes: int

    preview_text: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index("ix_resources_experiment", "experiment_id"),
        Index("ix_resources_run", "run_id"),
    )

    def _resolve_file_path(self) -> Path:
        """Resolve file path, trying DATA_DIR if stored path doesn't exist.

        This handles both local development and Docker container environments.

        Returns:
            Resolved Path object

        Raises:
            FileNotFoundError: If file cannot be found in any location
        """
        file_path = Path(self.file_path)

        # If path exists, return it directly
        if file_path.exists():
            return file_path

        # Import here to avoid circular dependency (loader imports models)
        # Type checker sees this via TYPE_CHECKING import above
        from h_arcane.benchmarks.gdpeval.loader import DATA_DIR  # noqa: PLC0415

        # If stored path is absolute, try to extract relative part
        if file_path.is_absolute():
            # Check if path contains "data/" and extract everything after it
            path_str = str(file_path)
            if "/data/" in path_str:
                # Extract relative part after "data/"
                relative_part = path_str.split("/data/", 1)[1]
                resolved_path = DATA_DIR / relative_part
            else:
                # Try treating the whole path as relative to DATA_DIR
                resolved_path = DATA_DIR / self.file_path
        else:
            # Path is already relative, resolve against DATA_DIR
            resolved_path = DATA_DIR / self.file_path

        if resolved_path.exists():
            return resolved_path
        else:
            # Provide helpful error message
            raise FileNotFoundError(
                f"Resource file not found. Tried:\n"
                f"  1. {file_path}\n"
                f"  2. {resolved_path}\n"
                f"  (DATA_DIR={DATA_DIR})"
            )

    def load_content(self) -> bytes:
        """Load file content from disk.

        Resolves paths relative to DATA_DIR if the stored path doesn't exist.
        This handles both local development and Docker container environments.
        """
        file_path = self._resolve_file_path()
        return file_path.read_bytes()

    def load_text(self) -> str:
        """Load file content as text.

        Resolves paths relative to DATA_DIR if the stored path doesn't exist.
        This handles both local development and Docker container environments.
        """
        file_path = self._resolve_file_path()
        return file_path.read_text()


class AgentConfig(SQLModel, table=True):
    """Agent configuration snapshot for a run."""

    __tablename__ = "agent_configs"  # type: ignore[assignment]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)

    # Agent identity
    name: str  # e.g., "TaskWorker"
    agent_type: str  # e.g., "react_worker"

    # Configuration snapshot
    model: str  # e.g., "gpt-4o"
    system_prompt: str
    tools: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (Index("ix_agent_configs_run", "run_id"),)


class Evaluation(SQLModel, table=True):
    """Aggregate evaluation result for a run."""

    __tablename__ = "evaluations"  # type: ignore[assignment]

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

    evaluated_at: datetime = Field(default_factory=datetime.utcnow)


class CriterionResult(SQLModel, table=True):
    """One row per (run, stage, criterion) — fully queryable."""

    __tablename__ = "criterion_results"  # type: ignore[assignment]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)

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


class TaskEvaluationResult(SQLModel, table=True):
    """Complete task evaluation result snapshot.

    Stores a complete evaluation result including all criterion results and aggregate scores.
    This provides a denormalized view/snapshot of the evaluation state for a run.
    """

    __tablename__ = "task_evaluation_results"  # type: ignore[assignment]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True, unique=True)

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

    created_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (Index("ix_task_evaluation_results_run", "run_id"),)
