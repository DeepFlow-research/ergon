"""Pydantic DTOs for the run detail API surface.

Adapted for definition-backed schema: task structure comes from
ExperimentDefinitionTask rows rather than a serialized task tree.

"""

from datetime import datetime
from typing import Any

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
    assigned_worker_name: str | None = None
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
    output_text: str | None = None
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
    criterion_type: str
    criterion_description: str
    evaluation_input: str
    score: float
    max_score: float
    feedback: str
    evaluated_action_ids: list[str] = Field(default_factory=list)
    evaluated_resource_ids: list[str] = Field(default_factory=list)
    error: dict[str, Any] | None = None  # slopcop: ignore[no-typing-any]


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


class RunCommunicationMessageDto(CamelModel):
    id: str
    thread_id: str
    thread_topic: str
    run_id: str
    task_id: str | None = None
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
    generation_turns_by_task: dict[str, list["RunGenerationTurnDto"]] = Field(default_factory=dict)
    threads: list[RunCommunicationThreadDto] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    total_tasks: int = 0
    total_leaf_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    running_tasks: int = 0
    final_score: float | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Generation turn DTO (RL observability)
# ---------------------------------------------------------------------------


class RunGenerationTurnDto(CamelModel):
    """One model generation turn in a task execution."""

    id: str
    task_execution_id: str
    worker_binding_key: str
    turn_index: int
    prompt_text: str | None = None
    raw_response: dict[str, Any]  # slopcop: ignore[no-typing-any]
    response_text: str | None = None
    tool_calls: list[dict[str, Any]] | None = None  # slopcop: ignore[no-typing-any]
    tool_results: list[dict[str, Any]] | None = None  # slopcop: ignore[no-typing-any]
    policy_version: str | None = None
    has_logprobs: bool = False
    created_at: str | None = None
    token_ids: list[int] | None = None
    logprobs: list[float] | None = None


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


# ---------------------------------------------------------------------------
# Run graph mutation DTO (Timeline scrubber)
# ---------------------------------------------------------------------------


class RunGraphMutationDto(BaseModel):
    """One entry in the append-only mutation log for a run.

    Field names are snake_case to match the frontend GraphMutationDtoSchema.
    """

    id: str
    run_id: str
    sequence: int
    mutation_type: str
    target_type: str
    target_id: str
    actor: str
    old_value: dict[str, object] | None
    new_value: dict[str, object]
    reason: str | None
    created_at: str
