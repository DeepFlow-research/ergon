"""Pydantic DTOs for the sample detail API surface.

Task structure comes from SampleGraphNode + SampleGraphEdge rows (the live graph),
and all task keys are SampleGraphNode.task_id.

"""

from datetime import datetime
from typing import Any
from uuid import UUID

from ergon_core.core.application.evaluation.summary import EvalCriterionStatus
from ergon_core.core.application.samples.event_views import (
    SampleRuntimeEventView as SampleEventView,
)
from ergon_core.core.shared.context_parts import ContextEventType, ContextPartChunkLog
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


class SampleCommunicationMessageDto(CamelModel):
    id: str
    thread_id: str
    thread_topic: str
    sample_id: str
    task_id: str | None = None
    task_attempt_id: str | None = None
    from_agent_id: str
    to_agent_id: str
    content: str
    sequence_num: int
    created_at: datetime


class SampleCommunicationThreadDto(CamelModel):
    id: str
    sample_id: str
    task_id: str | None = None
    topic: str
    summary: str | None = None
    agent_a_id: str
    agent_b_id: str
    created_at: datetime
    updated_at: datetime
    messages: list[SampleCommunicationMessageDto] = Field(default_factory=list)


class SampleTaskDto(CamelModel):
    """REST projection of SampleGraphNode for run detail pages.

    This is not the canonical graph schema; graph semantics live in
    application/graph/models.py and application/runtime/status.py.
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


class SampleResourceDto(CamelModel):
    id: str
    task_id: str
    task_attempt_id: str
    name: str
    mime_type: str
    file_path: str
    size_bytes: int
    created_at: datetime


class SampleExecutionAttemptDto(CamelModel):
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


class SampleEvaluationCriterionDto(CamelModel):
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


class SampleTaskEvaluationDto(CamelModel):
    id: str
    sample_id: str
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
    criterion_results: list[SampleEvaluationCriterionDto] = Field(default_factory=list)


class SampleSandboxCommandDto(CamelModel):
    command: str
    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None
    duration_ms: int | None = None
    timestamp: datetime


class SampleSandboxDto(CamelModel):
    sandbox_id: str
    task_id: str
    template: str | None = None
    timeout_minutes: int
    status: str
    created_at: datetime
    closed_at: datetime | None = None
    close_reason: str | None = None
    commands: list[SampleSandboxCommandDto] = Field(default_factory=list)


class SampleContextEventDto(CamelModel):
    id: UUID
    sample_id: UUID
    task_attempt_id: UUID
    task_id: UUID
    worker_binding_key: str
    sequence: int
    event_type: ContextEventType
    payload: ContextPartChunkLog
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class SampleSnapshotMetricsDto(CamelModel):
    sample_id: str
    status: str
    duration_ms: int | None = None
    total_tasks: int = 0
    tool_call_count: int = 0
    total_tokens: int | None = None
    token_breakdown: dict[str, int] = Field(default_factory=dict)
    total_cost_usd: float | None = None
    cost_observed: bool = False


class SampleSnapshotDto(CamelModel):
    id: str
    name: str
    status: str
    tasks: dict[str, SampleTaskDto] = Field(default_factory=dict)
    root_task_id: str = ""  # slopcop: ignore[no-str-empty-default]
    resources_by_task: dict[str, list[SampleResourceDto]] = Field(default_factory=dict)
    executions_by_task: dict[str, list[SampleExecutionAttemptDto]] = Field(default_factory=dict)
    evaluations_by_task: dict[str, SampleTaskEvaluationDto] = Field(default_factory=dict)
    sandboxes_by_task: dict[str, SampleSandboxDto] = Field(default_factory=dict)
    context_events_by_task: dict[str, list[SampleContextEventDto]] = Field(default_factory=dict)
    threads: list[SampleCommunicationThreadDto] = Field(default_factory=list)
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
    metrics: SampleSnapshotMetricsDto | None = None
    error: str | None = None


class SampleSummaryDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    name: str
    status: str
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    latest_activity_at: datetime | None = None
    duration_seconds: float | None = None
    experiment_id: UUID | None = None
    experiment: str | None = None
    benchmark_type: str
    instance_key: str
    sample_id: str | None = None
    sample_label: str
    evaluator_slug: str | None = None
    model_target: str | None = None
    final_score: float | None = None
    return_value: float | None = Field(default=None, alias="return")
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    running_tasks: int = 0
    cancelled_tasks: int = 0
    total_cost_usd: float | None = None
    error_message: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class SampleDetailView(CamelModel):
    sample_id: UUID
    experiment_id: UUID
    environment_id: UUID
    environment_name: str
    sample_key: str
    sample_ref: dict[str, Any] = Field(default_factory=dict)
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    status: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class SampleGraphNodeView(CamelModel):
    task_id: UUID
    task_slug: str
    description: str
    status: str
    parent_task_id: UUID | None = None
    level: int = 0
    assigned_worker_slug: str | None = None
    created_at: datetime
    updated_at: datetime


class SampleGraphEdgeView(CamelModel):
    edge_id: UUID
    source_task_id: UUID
    target_task_id: UUID
    status: str
    created_at: datetime
    updated_at: datetime


class SampleGraphView(CamelModel):
    nodes: list[SampleGraphNodeView] = Field(default_factory=list)
    edges: list[SampleGraphEdgeView] = Field(default_factory=list)


class SampleEventsView(CamelModel):
    items: list[SampleEventView] = Field(default_factory=list)


class SampleStateView(CamelModel):
    sample_id: UUID
    experiment_id: UUID
    environment_id: UUID
    environment_name: str
    detail: SampleDetailView
    events: list[SampleEventView] = Field(default_factory=list)
    graph: SampleGraphView = Field(default_factory=SampleGraphView)
