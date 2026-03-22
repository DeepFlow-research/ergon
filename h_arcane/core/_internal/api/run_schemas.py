"""Pydantic DTOs for the run detail API surface."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from h_arcane.core._internal.db.models import RunStatus
from h_arcane.core.status import TaskStatus


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
    id: str
    name: str
    description: str
    status: TaskStatus
    parent_id: str | None = None
    child_ids: list[str] = Field(default_factory=list)
    depends_on_ids: list[str] = Field(default_factory=list)
    assigned_worker_id: str | None = None
    assigned_worker_name: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    is_leaf: bool
    level: int


class RunActionDto(CamelModel):
    id: str
    task_id: str
    worker_id: str
    worker_name: str
    type: str
    input: str
    output: str | None = None
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    success: bool
    error: str | None = None


class RunResourceDto(CamelModel):
    id: str
    task_id: str
    task_execution_id: str
    name: str
    mime_type: str
    size_bytes: int
    file_path: str
    created_at: datetime


class RunExecutionAttemptDto(CamelModel):
    id: str
    task_id: str
    attempt_number: int
    status: TaskStatus
    agent_id: str | None = None
    agent_name: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    output_text: str | None = None
    output_resource_ids: list[str] = Field(default_factory=list)
    error_message: str | None = None
    score: float | None = None
    evaluation_details: dict[str, Any] = Field(default_factory=dict)


class RunCommunicationMessageDto(CamelModel):
    id: str
    thread_id: str
    run_id: str
    task_id: str | None = None
    thread_topic: str
    from_agent_id: str
    to_agent_id: str
    content: str
    sequence_num: int
    created_at: datetime


class RunCommunicationThreadDto(CamelModel):
    id: str
    run_id: str
    task_id: str | None = None
    topic: str
    agent_a_id: str
    agent_b_id: str
    created_at: datetime
    updated_at: datetime
    messages: list[RunCommunicationMessageDto] = Field(default_factory=list)


class RunEvaluationCriterionDto(CamelModel):
    id: str
    stage_num: int
    stage_name: str
    criterion_num: int
    criterion_type: str
    criterion_description: str
    score: float
    max_score: float
    feedback: str
    evaluation_input: str
    error: dict[str, Any] | None = None
    evaluated_action_ids: list[str] = Field(default_factory=list)
    evaluated_resource_ids: list[str] = Field(default_factory=list)


class RunTaskEvaluationDto(CamelModel):
    id: str
    run_id: str
    task_id: str | None = None
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


class RunSnapshotDto(CamelModel):
    id: str
    experiment_id: str
    name: str
    status: RunStatus
    tasks: dict[str, RunTaskDto] = Field(default_factory=dict)
    root_task_id: str = ""
    actions_by_task: dict[str, list[RunActionDto]] = Field(default_factory=dict)
    resources_by_task: dict[str, list[RunResourceDto]] = Field(default_factory=dict)
    executions_by_task: dict[str, list[RunExecutionAttemptDto]] = Field(default_factory=dict)
    sandboxes_by_task: dict[str, RunSandboxDto] = Field(default_factory=dict)
    threads: list[RunCommunicationThreadDto] = Field(default_factory=list)
    evaluations_by_task: dict[str, RunTaskEvaluationDto] = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    total_tasks: int = 0
    total_leaf_tasks: int = 0
    completed_tasks: int = 0
    running_tasks: int = 0
    failed_tasks: int = 0
    final_score: float | None = None
    error: str | None = None
