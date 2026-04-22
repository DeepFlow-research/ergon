"""Typed command/result DTOs for orchestration services.

These are the contracts between Inngest functions and services.
Adapted from ref: definition_id replaces experiment_id.
"""

import sys
from datetime import datetime

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):
        pass


from uuid import UUID

from pydantic import BaseModel, Field


class TaskDescriptor(BaseModel):
    """Lightweight task reference for orchestration steps."""

    model_config = {"frozen": True}

    task_id: UUID
    task_slug: str
    parent_task_id: UUID | None = None
    node_id: UUID | None = None


class InitializeWorkflowCommand(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    definition_id: UUID


class InitializedWorkflow(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    definition_id: UUID
    benchmark_type: str
    total_tasks: int
    total_root_tasks: int
    pending_tasks: list[TaskDescriptor] = Field(default_factory=list)
    initial_ready_tasks: list[TaskDescriptor] = Field(default_factory=list)


class PrepareTaskExecutionCommand(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    definition_id: UUID
    task_id: UUID
    node_id: UUID | None = None


class PreparedTaskExecution(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    definition_id: UUID
    task_id: UUID
    task_slug: str
    task_description: str
    benchmark_type: str
    assigned_worker_slug: str | None = None
    worker_type: str | None = None
    model_target: str | None = None
    execution_id: UUID
    node_id: UUID | None = None
    skipped: bool = False
    skip_reason: str | None = None


class FinalizeTaskExecutionCommand(BaseModel):
    model_config = {"frozen": True}

    execution_id: UUID
    final_assistant_message: str | None = None
    output_resource_ids: list[UUID] = Field(default_factory=list)


class FailTaskExecutionCommand(BaseModel):
    model_config = {"frozen": True}

    execution_id: UUID
    run_id: UUID
    task_id: UUID
    error_message: str


class WorkflowTerminalState(StrEnum):
    NONE = "none"
    COMPLETED = "completed"
    FAILED = "failed"


class PropagateTaskCompletionCommand(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    definition_id: UUID
    task_id: UUID
    execution_id: UUID
    node_id: UUID | None = None


class PropagationResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    definition_id: UUID
    completed_task_id: UUID
    ready_tasks: list[TaskDescriptor] = Field(default_factory=list)
    invalidated_targets: list[UUID] = Field(default_factory=list)
    workflow_terminal_state: WorkflowTerminalState = WorkflowTerminalState.NONE


class FinalizeWorkflowCommand(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    definition_id: UUID


class FinalizedWorkflowResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    final_score: float | None = None
    normalized_score: float | None = None
    evaluators_count: int = 0


class RunCompletionData(BaseModel):
    """Atomic bundle passed into run completion persistence."""

    model_config = {"frozen": True}

    completed_at: datetime
    final_score: float | None = None
    normalized_score: float | None = None
    total_cost_usd: float = 0.0
    output_text: str | None = None
    execution_result: dict[str, object] = Field(default_factory=dict)
