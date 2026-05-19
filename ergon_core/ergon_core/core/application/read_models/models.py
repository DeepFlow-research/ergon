"""Pydantic DTOs for the run detail API surface.

Task structure comes from RunGraphNode + RunGraphEdge rows (the live graph),
not from ExperimentDefinitionTask. All task keys are RunGraphNode.task_id.

"""

from datetime import datetime
from typing import Any
from uuid import UUID

from ergon_core.core.application.communication.models import RunCommunicationThreadDto
from ergon_core.core.application.graph.models import GraphMutationRecordDto
from ergon_core.core.persistence.context.event_payloads import (
    ContextEventPayload,
    ContextEventType,
)
from ergon_core.core.persistence.telemetry.evaluation_summary import EvalCriterionStatus
from ergon_core.core.persistence.telemetry.models import ExperimentCohortStatus
from ergon_core.core.shared.json_types import JsonObject
from pydantic import BaseModel, ConfigDict, Field


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class CamelModel(BaseModel):
    """Base model that exposes camelCase JSON to the frontend."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class RunTaskDto(CamelModel):
    """REST projection of RunGraphNode for run detail pages.

    This is not the canonical graph schema; graph semantics live in
    application/graph/models.py and persistence/graph/status_conventions.py.
    """

    id: str
    name: str
    description: str
    status: str
    parent_id: str | None = None
    child_ids: list[str] = Field(default_factory=list)
    depends_on_ids: list[str] = Field(default_factory=list)
    is_leaf: bool
    level: int
    assigned_worker_id: str | None = None
    assigned_worker_slug: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class RunResourceDto(CamelModel):
    id: str
    task_id: str
    task_execution_id: str
    name: str
    mime_type: str
    file_path: str
    size_bytes: int
    created_at: datetime


class RunExecutionAttemptDto(CamelModel):
    id: str
    task_id: str
    attempt_number: int
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    final_assistant_message: str | None = None
    error_message: str | None = None
    score: float | None = None
    agent_id: str | None = None
    agent_name: str | None = None
    evaluation_details: dict[str, Any] | None = None  # slopcop: ignore[no-typing-any]
    output_resource_ids: list[str] = Field(default_factory=list)


class RunEvaluationCriterionDto(CamelModel):
    id: str
    stage_num: int
    stage_name: str
    criterion_num: int
    criterion_slug: str
    criterion_type: str
    criterion_description: str
    criterion_name: str
    status: EvalCriterionStatus
    passed: bool
    weight: float
    contribution: float
    evaluation_input: str | None = None
    score: float
    max_score: float
    feedback: str | None = None
    model_reasoning: str | None = None
    skipped_reason: str | None = None
    evaluated_action_ids: list[str] = Field(default_factory=list)
    evaluated_resource_ids: list[str] = Field(default_factory=list)
    observation: dict[str, Any] | None = None  # slopcop: ignore[no-typing-any]
    error: dict[str, Any] | None = None  # slopcop: ignore[no-typing-any]


class RunTaskEvaluationDto(CamelModel):
    id: str
    run_id: str
    task_id: str | None = None
    evaluator_name: str
    aggregation_rule: str
    total_score: float
    max_score: float
    normalized_score: float
    stages_evaluated: int
    stages_passed: int
    failed_gate: str | None = None
    created_at: datetime
    criterion_results: list[RunEvaluationCriterionDto] = Field(default_factory=list)


class RunSandboxCommandDto(CamelModel):
    command: str
    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None
    duration_ms: int | None = None
    timestamp: datetime


class RunSandboxDto(CamelModel):
    sandbox_id: str
    task_id: str
    template: str | None = None
    timeout_minutes: int
    status: str
    created_at: datetime
    closed_at: datetime | None = None
    close_reason: str | None = None
    commands: list[RunSandboxCommandDto] = Field(default_factory=list)


class RunContextEventDto(CamelModel):
    id: UUID
    run_id: UUID
    task_execution_id: UUID
    task_node_id: UUID
    worker_binding_key: str
    sequence: int
    event_type: ContextEventType
    payload: ContextEventPayload
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class RunSnapshotDto(CamelModel):
    id: str
    experiment_id: str
    name: str
    status: str
    tasks: dict[str, RunTaskDto] = Field(default_factory=dict)
    root_task_id: str = ""  # slopcop: ignore[no-str-empty-default]
    resources_by_task: dict[str, list[RunResourceDto]] = Field(default_factory=dict)
    executions_by_task: dict[str, list[RunExecutionAttemptDto]] = Field(default_factory=dict)
    evaluations_by_task: dict[str, RunTaskEvaluationDto] = Field(default_factory=dict)
    sandboxes_by_task: dict[str, RunSandboxDto] = Field(default_factory=dict)
    context_events_by_task: dict[str, list[RunContextEventDto]] = Field(default_factory=dict)
    threads: list[RunCommunicationThreadDto] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    total_tasks: int = 0
    total_leaf_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    running_tasks: int = 0
    cancelled_tasks: int = 0
    final_score: float | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Training DTOs (RL observability)
# ---------------------------------------------------------------------------


class TrainingCurvePointDto(CamelModel):
    run_id: str
    step: int
    mean_score: float
    benchmark_type: str | None = None
    created_at: str | None = None


class TrainingSessionDto(CamelModel):
    id: str
    experiment_definition_id: str
    model_name: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    output_dir: str | None = None
    total_steps: int | None = None
    final_loss: float | None = None


class TrainingMetricDto(CamelModel):
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


class CohortStatusCountsDto(BaseModel):
    """Aggregate run counts by lifecycle status."""

    pending: int = 0
    executing: int = 0
    evaluating: int = 0
    completed: int = 0
    failed: int = 0


class CohortSummaryDto(BaseModel):
    """Summary row for cohort list and live updates."""

    cohort_id: UUID
    name: str
    description: str | None = None
    created_by: str | None = None
    created_at: datetime
    status: str
    total_runs: int = 0
    status_counts: CohortStatusCountsDto = Field(default_factory=CohortStatusCountsDto)
    average_score: float | None = None
    best_score: float | None = None
    worst_score: float | None = None
    average_duration_ms: int | None = None
    failure_rate: float = 0.0
    stats_updated_at: datetime | None = None


class CohortExperimentRowDto(BaseModel):
    """One experiment inside a cohort detail view."""

    experiment_id: UUID
    name: str
    benchmark_type: str
    sample_count: int
    total_runs: int = 0
    status_counts: CohortStatusCountsDto = Field(default_factory=CohortStatusCountsDto)
    status: str
    created_at: datetime
    default_model_target: str | None = None
    default_evaluator_slug: str | None = None
    final_score: float | None = None
    total_cost_usd: float | None = None
    error_message: str | None = None


class CohortDetailDto(BaseModel):
    """Full payload for a single cohort detail page."""

    summary: CohortSummaryDto
    experiments: list[CohortExperimentRowDto] = Field(default_factory=list)


class UpdateCohortRequest(BaseModel):
    """Mutable cohort fields exposed through the operator API."""

    status: ExperimentCohortStatus


class ResolveCohortRequest(BaseModel):
    """Request to resolve or create a cohort by name."""

    name: str
    description: str | None = None
    created_by: str | None = None
    metadata: JsonObject = Field(default_factory=dict)
